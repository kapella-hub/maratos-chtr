"""Base agent interface."""

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator
from uuid import uuid4

from app.config import settings
from app.tools import ToolResult, registry as tool_registry

# Import thinking module for structured thinking
try:
    from app.thinking import (
        ThinkingManager,
        ThinkingLevel,
        ThinkingSession,
        ThinkingBlock,
        AdaptiveThinkingManager,
        ThinkingMetrics,
        get_template,
        detect_template,
    )
    from app.thinking.adaptive import determine_thinking_level
    from app.thinking.metrics import get_metrics
    THINKING_AVAILABLE = True
except ImportError:
    THINKING_AVAILABLE = False

logger = logging.getLogger(__name__)

# Import kiro provider for LLM access
# All LLM calls are routed through kiro-cli
try:
    from app.llm import kiro_provider, KiroProvider
    from app.llm.kiro_provider import KiroConfig
    KIRO_AVAILABLE = True
except ImportError:
    KIRO_AVAILABLE = False
    logger.warning("Kiro provider not available, LLM calls will fail")


# kiro-cli model names (used directly, no translation needed)
KIRO_MODELS = [
    "Auto",
    "claude-opus-4.5",
    "claude-sonnet-4.5",
    "claude-sonnet-4",
    "claude-haiku-4.5",
]


# Regex to detect numbered line format: "1: code", "• 1: code", "1, 1: code" (diff), "  220: code" (indented)
NUMBERED_LINE_PATTERN = re.compile(r'^\s*(?:[•\-\*]\s*)?(\d+)(?:,\s*\d+)?\s*:\s?(.*)$')


def convert_numbered_lines_to_codeblock(text: str) -> str:
    """Convert consecutive numbered lines (1: code, 2: code) to proper markdown code blocks.

    Detects patterns like:
        1: # Database Configuration
        2: DATABASE_URL=postgres://...
        3:

    And converts them to:
        ```
        # Database Configuration
        DATABASE_URL=postgres://...

        ```
    """
    lines = text.split('\n')
    result = []
    code_block_lines = []
    in_code_block = False
    last_line_num = 0

    for line in lines:
        match = NUMBERED_LINE_PATTERN.match(line)

        if match:
            line_num = int(match.group(1))
            code_content = match.group(2)

            # Check if this continues a sequence (allow gaps up to 10 for diff output with removed lines)
            if not in_code_block or (line_num > last_line_num and line_num <= last_line_num + 10):
                if not in_code_block:
                    in_code_block = True
                code_block_lines.append(code_content)
                last_line_num = line_num
            else:
                # New sequence - flush previous block
                if code_block_lines:
                    result.append('```')
                    result.extend(code_block_lines)
                    result.append('```')
                code_block_lines = [code_content]
                last_line_num = line_num
                in_code_block = True
        else:
            # Non-numbered line - flush any accumulated code block
            if code_block_lines:
                result.append('```')
                result.extend(code_block_lines)
                result.append('```')
                code_block_lines = []
                in_code_block = False
                last_line_num = 0
            result.append(line)

    # Flush any remaining code block
    if code_block_lines:
        result.append('```')
        result.extend(code_block_lines)
        result.append('```')

    text_result = '\n'.join(result)

    # Secondary pass: Wrap "File: ... \n python ..." patterns
    # Matches:
    # 1. File: ... (header)
    # 2. Optional newlines
    # 3. (python|...) (language identifier start of code)
    # 4. Content until double newline or end
    
    lang_ids = {'python', 'javascript', 'typescript', 'java', 'html', 'css', 'bash', 'sh', 'yaml', 'json', 'sql', 'go', 'rust'}
    
    def code_block_replacer(match):
        header = match.group(1)
        spacing = match.group(2)
        content = match.group(3)
        
        # If content already has backticks, don't wrap
        if '```' in content:
            return match.group(0)
            
        # Extract lang if present at start of content
        first_line = content.split('\n')[0].strip()
        first_word = first_line.split(' ')[0].lower() if first_line else ""
        
        lang = first_word if first_word in lang_ids else ""
        
        return f"{header}\n{spacing}```{lang}\n{content}\n```"

    pattern = re.compile(
        r'^(File:.+?)(\n+)(?=(?:python|javascript|typescript|bash|sh|html|css|yaml|json|sql|go|rust)\b)(.+?)(?=\n\n|━━━━━━━━|-----|\Z)', 
        re.MULTILINE | re.DOTALL
    )
    
    return pattern.sub(code_block_replacer, text_result)


@dataclass
class AgentConfig:
    """Configuration for an agent."""

    id: str
    name: str
    description: str
    icon: str = "🤖"
    model: str = ""
    temperature: float = 0.7
    system_prompt: str = ""
    tools: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.model:
            self.model = settings.default_model


@dataclass
class Message:
    """Chat message."""

    role: str  # system, user, assistant, tool
    content: str
    tool_calls: list[dict] | None = None
    tool_call_id: str | None = None
    name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for LLM API."""
        d: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.tool_calls:
            d["tool_calls"] = self.tool_calls
        if self.tool_call_id:
            d["tool_call_id"] = self.tool_call_id
        if self.name:
            d["name"] = self.name
        return d


class Agent:
    """Base agent class."""

    def __init__(self, config: AgentConfig) -> None:
        self.config = config
        self._tool_schemas = tool_registry.get_schemas(config.tools) if config.tools else []
        self._thinking_manager = ThinkingManager() if THINKING_AVAILABLE else None
        self._current_thinking_session: ThinkingSession | None = None

    @property
    def id(self) -> str:
        return self.config.id

    @property
    def name(self) -> str:
        return self.config.name

    def get_system_prompt(self, context: dict[str, Any] | None = None) -> tuple[str, list]:
        """Get system prompt, optionally with context.

        Returns:
            Tuple of (prompt_string, matched_skills_list)
        """
        prompt = self.config.system_prompt
        matched_skills = []

        if context:
            # AUTO-SELECT SKILLS: Check for matching skills based on task/query
            skill_context, matched_skills = self._get_skill_context(context)
            if skill_context:
                prompt += f"\n\n{skill_context}"

            # Inject project context (conventions, patterns, tech stack)
            if "project" in context and context["project"]:
                prompt += f"\n\n{context['project']}\n"

            # Inject rules (development standards, guidelines)
            if "rules" in context and context["rules"]:
                prompt += f"\n\n{context['rules']}\n"

            # Inject workspace path
            if "workspace" in context:
                prompt += f"\n\n## Workspace\nAll file modifications must be in: `{context['workspace']}`\n"

            # Inject memory context (CRITICAL for accuracy)
            if "memory" in context and context["memory"]:
                prompt += f"\n\n## Relevant Context from Memory\n{context['memory']}\n"

            # Inject file context
            if "files" in context:
                prompt += f"\n\n## Files to Work With\n{context['files']}\n"

            # Inject Thinking Lessons (Thinking 3.0)
            if THINKING_AVAILABLE and "user_message" in context and context["user_message"]:
                try:
                    from app.thinking.memory import get_thinking_memory
                    import hashlib
                    memory = get_thinking_memory()
                    
                    # Derive project_id from workspace
                    project_id = None
                    if "workspace" in context and context["workspace"]:
                        project_id = hashlib.md5(context["workspace"].encode()).hexdigest()[:8]
                        
                    lessons = memory.search_lessons(context["user_message"], project_id=project_id)
                    if lessons:
                        prompt += "\n\n## Lessons from Past Critiques\n"
                        prompt += "Apply these insights to avoid repeating mistakes:\n"
                        for lesson in lessons:
                            prompt += f"- {lesson.critique}\n"
                except Exception as e:
                    logger.warning(f"Failed to inject thinking lessons: {e}")

        # Inject Thinking Level Instructions using the thinking module
        if THINKING_AVAILABLE:
            base_level = ThinkingLevel.from_string(settings.thinking_level or "medium")

            # Use adaptive thinking if we have a user message
            user_message = context.get("user_message", "") if context else ""
            if user_message:
                adaptive_result = determine_thinking_level(user_message, base_level, context)
                thinking_level = adaptive_result.adaptive_level
                template = adaptive_result.template

                # Store adaptive result for metrics
                if context is not None:
                    context["_adaptive_thinking"] = adaptive_result.to_dict()
            else:
                thinking_level = base_level
                template = None

            if thinking_level != ThinkingLevel.OFF:
                prompt += f"\n\n## Thinking Mode\n**Level:** {thinking_level.value.upper()} - {thinking_level.description}\n"

                # Add template-specific guidance
                if template and self._thinking_manager:
                    prompt += self._thinking_manager.generate_thinking_prompt(thinking_level, template.id)
                else:
                    prompt += self._thinking_manager.generate_thinking_prompt(thinking_level) if self._thinking_manager else ""

                prompt += "\n\nWrap your thinking in <thinking>...</thinking> tags. This will be processed but not shown to the user.\n"
        else:
            # Fallback to old behavior if thinking module not available
            thinking_level_str = settings.thinking_level or "medium"
            if thinking_level_str != "off":
                prompt += f"\n\n## Current Thinking Level\n**{thinking_level_str.upper()}** - "
                level_descriptions = {
                    "minimal": "Quick sanity check before execution",
                    "low": "Brief problem breakdown",
                    "medium": "Structured analysis with approach evaluation",
                    "high": "Deep analysis, multiple approaches, risk assessment",
                    "max": "Exhaustive analysis with self-critique",
                }
                prompt += level_descriptions.get(thinking_level_str, "Standard analysis")
                prompt += "\n"

        return prompt, matched_skills

    def _get_skill_context(self, context: dict[str, Any]) -> tuple[str, list]:
        """Find matching skills and generate context to inject.

        Returns:
            Tuple of (context_string, matched_skills_list)
        """
        try:
            from app.skills.base import skill_registry
        except ImportError:
            return "", []

        matched_skills = []

        # Check for explicit skill
        if "skill_id" in context:
            skill = skill_registry.get(context["skill_id"])
            if skill:
                matched_skills.append(skill)

        # Check task/query/user_message for triggers
        for key in ["task", "query", "user_message"]:
            if key in context and context[key]:
                for skill in skill_registry.find_by_trigger(context[key]):
                    if skill not in matched_skills:
                        matched_skills.append(skill)

        if not matched_skills:
            return "", []

        # Generate skill context
        parts = ["## 🎯 Applicable Skills Detected"]
        parts.append("The following skills have been auto-selected based on your task. Follow their guidelines:\n")

        for skill in matched_skills:
            logger.info(f"Auto-selected skill: {skill.id} for agent {self.id}")
            parts.append(f"### {skill.name}")
            parts.append(skill.to_kiro_context())
            parts.append("")

        return "\n".join(parts), matched_skills

    def _should_auto_execute_workflow(self, skill, user_message: str) -> bool:
        """Decide if skill workflow should auto-execute based on task complexity."""
        if not skill.workflow or len(skill.workflow) < 3:
            return False
        if len(user_message) < 50:
            return False
        # Check for auto_execute flag in skill (default False)
        return getattr(skill, 'auto_execute', False) or skill.id in ['bug-fix', 'security-review', 'refactor']

    async def maybe_execute_skill_workflows(
        self, 
        context: dict[str, Any], 
        user_message: str
    ) -> AsyncIterator[str]:
        """Execute skill workflows if conditions are met. Yields progress updates."""
        from app.skills.executor import SkillExecutor
        
        _, matched_skills = self._get_skill_context(context)
        
        for skill in matched_skills:
            if self._should_auto_execute_workflow(skill, user_message):
                yield f"\n\n🎯 **Auto-executing {skill.name} workflow...**\n"
                
                executor = SkillExecutor(context.get("workspace"))
                exec_context = {
                    "bug_description": user_message,
                    "task": user_message,
                    "files": context.get("files", ""),
                }
                
                result = await executor.execute(skill, exec_context)
                
                if result["success"]:
                    yield f"\n**✅ Workflow Completed** ({result['steps_run']} steps)\n\n"
                else:
                    yield f"\n**⚠️ Workflow - Partial Success**\n\n"
                
                for step_result in result["results"]:
                    status = "✅" if step_result["success"] else "❌"
                    step_name = step_result['step'].replace('_', ' ').title()
                    error_msg = f" - {step_result.get('error')}" if not step_result["success"] and step_result.get('error') else ""
                    yield f"- {status} **{step_name}**{error_msg}\n"
                
                yield "\n*Proceeding with conversation...*\n"

    async def chat(
        self,
        messages: list[Message],
        context: dict[str, Any] | None = None,
        model_override: str | None = None,
        temperature_override: float | None = None,
        max_tokens_override: int | None = None,
    ) -> AsyncIterator[str]:
        """Chat with the agent, yielding response chunks.

        All LLM calls are routed through kiro-cli.

        Args:
            messages: List of conversation messages
            context: Optional context dict (workspace, memory, files, etc.)
            model_override: Optional model to use instead of agent's default
            temperature_override: Optional temperature (not used with kiro)
            max_tokens_override: Optional max tokens (not used with kiro)
        """
        if not KIRO_AVAILABLE:
            yield "Error: Kiro provider not available. Please ensure kiro-cli is installed."
            return

        # Check kiro-cli availability
        if not await kiro_provider.is_available():
            yield "Error: kiro-cli not found. Please install: curl -fsSL https://cli.kiro.dev/install | bash"
            return

        # Initialize thinking session for this message
        message_id = str(uuid4())[:8]
        thinking_session: ThinkingSession | None = None
        thinking_start_time: float | None = None

        if THINKING_AVAILABLE and self._thinking_manager:
            base_level = ThinkingLevel.from_string(settings.thinking_level or "medium")
            # Get user message for adaptive thinking
            user_message = ""
            if messages:
                for msg in reversed(messages):
                    if msg.role == "user":
                        user_message = msg.content
                        break

            if context is None:
                context = {}
            context["user_message"] = user_message

            # Determine adaptive level
            adaptive_result = determine_thinking_level(user_message, base_level, context)
            
            # Derive project_id
            project_id = None
            active_project_name = None
            if context and "workspace" in context and context["workspace"]:
                import hashlib
                project_id = hashlib.md5(context["workspace"].encode()).hexdigest()[:8]
            
            if context and "active_project_name" in context:
                active_project_name = context["active_project_name"]

            thinking_session = await self._thinking_manager.create_session(
                message_id=message_id,
                level=adaptive_result.adaptive_level,
                complexity_score=adaptive_result.complexity_score,
                project_id=project_id,
                active_project_name=active_project_name,
            )
            thinking_session.original_level = base_level
            thinking_session.adaptive_level = adaptive_result.adaptive_level
            self._current_thinking_session = thinking_session

        # Build message list
        api_messages = []

        # System prompt and matched skills
        system_prompt, _ = self.get_system_prompt(context)
        if system_prompt:
            api_messages.append({"role": "system", "content": system_prompt})

        # Conversation messages
        for m in messages:
            if isinstance(m, dict):
                api_messages.append(m)
            elif hasattr(m, "to_dict"):
                api_messages.append(m.to_dict())
            else:
                # Fallback for unexpected types
                logger.warning(f"Unexpected message type in chat: {type(m)}")
                api_messages.append(dict(m))

        # Get model - use kiro-cli friendly names
        model = model_override or self.config.model
        # Convert to kiro-cli short model name
        model = _kiro_model_name(model)

        # Configure kiro (tools disabled - MaratOS handles tools via text parsing)
        kiro_config = KiroConfig(
            model=model,
            interactive=False,
            timeout=settings.llm_timeout,
            workdir=context.get("workspace") if context else None,
        )

        logger.info(f"Agent {self.id} calling kiro-cli with model={model}")

        # Buffer for filtering <thinking> and <analysis> blocks
        buffer = ""
        thinking_buffer = ""  # Accumulate thinking content for metrics
        in_hidden_block = False
        hidden_tag = ""  # Which tag we're currently inside
        current_block: ThinkingBlock | None = None

        try:
            async for chunk in kiro_provider.chat_completion_stream(api_messages, kiro_config):
                # Add chunk to buffer
                buffer += chunk

                # Hidden tags to filter out (thinking shows indicator, analysis is silent)
                hidden_tags = ["thinking", "analysis"]

                # Process buffer to filter hidden blocks
                while True:
                    if in_hidden_block:
                        # Look for closing tag
                        end_tag = f"</{hidden_tag}>"
                        end_idx = buffer.find(end_tag)
                        if end_idx != -1:
                            # Capture thinking content before discarding
                            thinking_buffer += buffer[:end_idx]

                            # Complete the thinking block with parsed steps
                            if current_block and thinking_session and self._thinking_manager:
                                steps = self._thinking_manager.parse_legacy_content(thinking_buffer)
                                duration_ms = int((time.time() - thinking_start_time) * 1000) if thinking_start_time else 0
                                for step in steps:
                                    step.duration_ms = duration_ms // max(len(steps), 1)
                                    current_block.add_step(step)
                                await self._thinking_manager.complete_block(current_block, thinking_session)

                            # Discard everything up to and including closing tag
                            buffer = buffer[end_idx + len(end_tag):]
                            thinking_buffer = ""

                            # Signal end of thinking block with structured data
                            if hidden_tag == "thinking":
                                if current_block and THINKING_AVAILABLE:
                                    # Yield structured thinking complete event
                                    yield f"__THINKING_COMPLETE__:{json.dumps(current_block.to_dict())}"
                                else:
                                    yield "__THINKING_END__"

                            in_hidden_block = False
                            hidden_tag = ""
                            current_block = None
                        else:
                            # Still in hidden block, accumulate thinking content
                            thinking_buffer += buffer
                            buffer = ""
                            break
                    else:
                        # Look for any opening tag
                        found_tag = None
                        found_idx = -1
                        for tag in hidden_tags:
                            idx = buffer.find(f"<{tag}>")
                            if idx != -1 and (found_idx == -1 or idx < found_idx):
                                found_idx = idx
                                found_tag = tag

                        if found_tag:
                            # Yield content before the tag
                            if found_idx > 0:
                                yield buffer[:found_idx]
                            buffer = buffer[found_idx + len(found_tag) + 2:]  # +2 for < and >
                            in_hidden_block = True
                            hidden_tag = found_tag
                            thinking_buffer = ""
                            thinking_start_time = time.time()

                            # Start a thinking block
                            if found_tag == "thinking" and thinking_session and self._thinking_manager:
                                # Detect template from user message
                                template = detect_template(context.get("user_message", "")) if THINKING_AVAILABLE and context else None
                                current_block = self._thinking_manager.start_block(
                                    thinking_session,
                                    template=template.id if template else None,
                                )
                                # Yield structured thinking start event
                                yield f"__THINKING_START__:{json.dumps({'block_id': current_block.id, 'level': thinking_session.effective_level.value})}"
                            elif found_tag == "thinking":
                                yield "__THINKING_START__"
                        else:
                            # No hidden tag, but keep potential partial tag in buffer
                            # Only yield up to last '<' to avoid splitting a tag
                            last_lt = buffer.rfind("<")
                            if last_lt > 0:
                                yield buffer[:last_lt]
                                buffer = buffer[last_lt:]
                            elif last_lt == -1:
                                # No '<' at all, safe to yield everything
                                yield buffer
                                buffer = ""
                            break

            # Flush remaining buffer (if not in hidden block)
            if buffer and not in_hidden_block:
                yield buffer

            # Record thinking metrics
            if thinking_session and THINKING_AVAILABLE:
                try:
                    metrics = get_metrics()
                    metrics.record(thinking_session, outcome="success")
                except Exception as e:
                    logger.debug(f"Failed to record thinking metrics: {e}")

        except Exception as e:
            logger.error(f"Kiro chat error for agent {self.id}: {e}", exc_info=True)

            # Record error in metrics
            if thinking_session and THINKING_AVAILABLE:
                try:
                    metrics = get_metrics()
                    metrics.record(thinking_session, outcome="error")
                except Exception:
                    pass

            yield f"\n\n⚠️ **Error:** {str(e)}\n"

        finally:
            # Clean up thinking session
            if thinking_session and self._thinking_manager:
                self._thinking_manager.close_session(thinking_session.id)
                self._current_thinking_session = None


    async def run_tool(
        self,
        tool_id: str,
        session_id: str | None = None,
        task_id: str | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        """Run a specific tool with guardrails enforcement.

        Args:
            tool_id: The tool to execute
            session_id: Optional session ID for tracking
            task_id: Optional task ID for tracking
            **kwargs: Tool parameters

        Returns:
            ToolResult from the tool execution
        """
        from app.tools.executor import tool_executor

        # Use tool_executor which enforces guardrails
        return await tool_executor.execute(
            tool_id=tool_id,
            session_id=session_id,
            task_id=task_id,
            agent_id=self.id,
            **kwargs,
        )

    async def chat_with_tools(
        self,
        messages: list[Message],
        context: dict[str, Any] | None = None,
        session_id: str | None = None,
        task_id: str | None = None,
    ) -> AsyncIterator[str]:
        """Chat with agent, executing tool calls in a loop.

        This method handles the multi-step tool execution loop:
        1. LLM emits response (may contain tool calls)
        2. System parses and executes tool calls
        3. System feeds results back to LLM
        4. Repeat until LLM emits final answer (no tool calls)

        Yields chunks including special events:
        - __TOOL_CALL__:{json} - Tool call detected
        - __TOOL_RESULT__:{json} - Tool execution result
        - __TOOL_ERROR__:{json} - Tool execution error
        - Regular content chunks

        Args:
            messages: Conversation messages
            context: Optional context (workspace, memory, etc.)
            session_id: Session ID for audit logging
            task_id: Task ID for audit logging
        """
        from app.tools.interpreter import (
            ToolInterpreter,
            InterpreterContext,
            ToolPolicy,
            has_tool_calls,
        )

        # Create interpreter with policy based on agent's allowed tools
        workspace = context.get("workspace") if context else None
        policy = ToolPolicy(
            allowed_tools=self.config.tools if self.config.tools else None,
            max_iterations=6,
            per_call_timeout_seconds=300.0,
            workspace_path=workspace,
        )

        interpreter_context = InterpreterContext(
            session_id=session_id,
            task_id=task_id,
            agent_id=self.id,
            policy=policy,
        )
        interpreter = ToolInterpreter(context=interpreter_context)

        # Working copy of messages for the loop
        working_messages = list(messages)
        accumulated_response = ""

        while True:
            # Check iteration limit
            can_continue, error = interpreter.check_iteration_limit()
            if not can_continue:
                yield f"__TOOL_ERROR__:{json.dumps({'error': error})}"
                yield f"\n\n⚠️ {error}. Returning partial response.\n\n"
                # Yield accumulated content without tool blocks
                clean_content = interpreter.strip_tool_blocks(accumulated_response)
                if clean_content:
                    yield clean_content
                return

            interpreter.increment_iteration()

            # Collect full response from this iteration
            iteration_response = ""
            async for chunk in self.chat(working_messages, context):
                # Pass through thinking events
                if chunk.startswith("__THINKING"):
                    yield chunk
                    continue
                iteration_response += chunk
                # Stream non-tool content immediately
                if not has_tool_calls(chunk):
                    yield chunk

            accumulated_response = iteration_response

            # Check for tool calls
            if not interpreter.has_tool_calls(iteration_response):
                # No tool calls - we're done
                logger.info(f"Agent {self.id} completed after {interpreter_context.iteration} iterations")
                return

            # Parse tool calls
            invocations = interpreter.parse(iteration_response)

            if not invocations:
                # No valid invocations found
                return

            # Check if repair is needed
            needs_repair, broken = interpreter.needs_repair(invocations)
            if needs_repair and broken:
                interpreter.mark_repair_attempted()
                repair_prompt = interpreter.get_repair_prompt(broken)
                working_messages.append(Message(role="assistant", content=iteration_response))
                working_messages.append(Message(role="user", content=repair_prompt))
                yield f"__TOOL_ERROR__:{json.dumps({'error': 'Invalid JSON, requesting repair', 'raw': broken.raw_json[:200]})}"
                continue

            # Emit tool call events
            for inv in invocations:
                if not inv.parse_error:
                    # Redact sensitive args for the event
                    safe_args = {k: v if k not in ("content", "password", "token") else "[REDACTED]"
                                for k, v in inv.args.items()}
                    yield f"__TOOL_CALL__:{json.dumps({'tool': inv.tool_id, 'args': safe_args})}"

            # Execute tools
            results = await interpreter.execute(invocations)

            # Emit result events
            for result in results:
                event_data = {
                    "tool": result.invocation.tool_id,
                    "success": result.result.success,
                    "duration_ms": round(result.duration_ms, 2),
                }
                if result.result.error:
                    event_data["error"] = result.result.error
                else:
                    # Include truncated output summary
                    output = result.result.output
                    event_data["output_length"] = len(output)
                    if len(output) <= 200:
                        event_data["output_preview"] = output
                    else:
                        event_data["output_preview"] = output[:200] + "..."

                yield f"__TOOL_RESULT__:{json.dumps(event_data)}"

                # Record tool usage for collaborative memory
                if self._thinking_manager and self._current_thinking_session:
                    try:
                        await self._thinking_manager.record_tool_usage(
                            session=self._current_thinking_session,
                            tool_name=result.invocation.tool_id,
                            tool_args=result.invocation.args,
                            success=result.result.success,
                            output=result.result.output
                        )
                    except Exception as e:
                        logger.warning(f"Failed to record tool usage: {e}")

            # Format results for next LLM turn
            results_message = interpreter.format_results(results)

            # Add assistant response and tool results to messages
            working_messages.append(Message(role="assistant", content=iteration_response))
            working_messages.append(Message(role="user", content=results_message))

            logger.info(
                f"Agent {self.id} iteration {interpreter_context.iteration}: "
                f"{len(invocations)} tool calls executed"
            )


def _kiro_model_name(model: str) -> str:
    """Convert model ID to kiro-cli friendly name.

    Handles legacy anthropic/ prefixes and full model IDs.
    """
    # Strip any provider prefix (legacy support)
    if "/" in model:
        model = model.split("/")[-1]

    # Map full model IDs to short names
    model_map = {
        "claude-opus-4-5-20251101": "claude-opus-4.5",
        "claude-sonnet-4-5-20241022": "claude-sonnet-4.5",
        "claude-sonnet-4-20250514": "claude-sonnet-4",
        "claude-haiku-4-5-20241022": "claude-haiku-4.5",
        "claude-3-opus-20240229": "claude-opus-4.5",
        "claude-3-sonnet-20240229": "claude-sonnet-4",
        "claude-3-haiku-20240307": "claude-haiku-4.5",
        "claude-3-5-sonnet-20241022": "claude-sonnet-4.5",
    }
    return model_map.get(model, model)
