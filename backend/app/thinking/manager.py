"""ThinkingManager - Core class for handling thinking operations.

Manages thinking sessions, blocks, and steps. Provides methods for
parsing thinking content and generating structured output.
"""

import json
import re
import time
from typing import Any, AsyncIterator
from uuid import uuid4

from app.thinking.models import (
    ThinkingLevel,
    ThinkingStepType,
    ThinkingStep,
    ThinkingBlock,
    ThinkingSession,
)


class ThinkingManager:
    """Manages thinking operations for AI responses.

    Handles:
    - Creating and managing thinking sessions
    - Parsing thinking content from various formats
    - Generating structured thinking output
    - Converting between formats (XML tags <-> JSON)
    """

    # Patterns for parsing legacy XML-style thinking tags
    THINKING_START_PATTERN = re.compile(r"<thinking>|<analysis>|\[THINKING\]", re.IGNORECASE)
    THINKING_END_PATTERN = re.compile(r"</thinking>|</analysis>|\[/THINKING\]", re.IGNORECASE)

    # Pattern for parsing step markers within thinking blocks
    # Pattern for parsing step markers within thinking blocks
    # Handles: [ANALYSIS], # Analysis, **Analysis**, Analysis
    # Pattern for parsing step markers within thinking blocks
    # Handles: [ANALYSIS], # Analysis, **Analysis**, Analysis
    STEP_PATTERN = re.compile(
        r"(?:^|\n)\s*(?:\[|#+\s*|\*\*?|)(?P<type>ANALYSIS|EVALUATION|DECISION|VALIDATION|RISK|IMPLEMENTATION|CRITIQUE|TOOL_CALL|TOOL_RESULT)(?:\]|:|\*\*?|)\s*\n?"
        r"(?P<content>.*?)(?=(?:^|\n)\s*(?:\[|#+\s*|\*\*?|)(?:ANALYSIS|EVALUATION|DECISION|VALIDATION|RISK|IMPLEMENTATION|CRITIQUE|TOOL_CALL|TOOL_RESULT)(?:\]|:|\*\*?|)|\Z)",
        re.IGNORECASE | re.DOTALL
    )

    def __init__(self, default_level: ThinkingLevel = ThinkingLevel.MEDIUM):
        """Initialize the thinking manager.

        Args:
            default_level: Default thinking level when not specified
        """
        self.default_level = default_level
        self._active_sessions: dict[str, ThinkingSession] = {}

    async def create_session(
        self,
        message_id: str,
        level: ThinkingLevel | None = None,
        complexity_score: float = 0.5,
        project_id: str | None = None,
        active_project_name: str | None = None,
    ) -> ThinkingSession:
        """Create a new thinking session for a message.

        Args:
            message_id: ID of the message this session is for
            level: Thinking level to use (or default)
            complexity_score: Estimated complexity of the task (0.0-1.0)

        Returns:
            New ThinkingSession
        """
        session = ThinkingSession(
            message_id=message_id,
            original_level=level or self.default_level,
            complexity_score=complexity_score,
            project_id=project_id,
            active_project_name=active_project_name,
        )
        self._active_sessions[session.id] = session
        return session

    def get_session(self, session_id: str) -> ThinkingSession | None:
        """Get an active thinking session by ID."""
        return self._active_sessions.get(session_id)

    def close_session(self, session_id: str) -> ThinkingSession | None:
        """Close and return a thinking session."""
        return self._active_sessions.pop(session_id, None)

    def start_block(
        self,
        session: ThinkingSession,
        template: str | None = None,
    ) -> ThinkingBlock:
        """Start a new thinking block within a session.

        Args:
            session: The thinking session
            template: Optional template name for this block

        Returns:
            New ThinkingBlock
        """
        block = ThinkingBlock(
            level=session.effective_level,
            template=template,
        )
        session.add_block(block)
        return block

    def add_step(
        self,
        block: ThinkingBlock,
        step_type: ThinkingStepType,
        content: str,
        duration_ms: int = 0,
        tokens: int = 0,
    ) -> ThinkingStep:
        """Add a step to a thinking block.

        Args:
            block: The thinking block
            step_type: Type of thinking step
            content: Content of the step
            duration_ms: Time taken for this step
            tokens: Tokens used for this step

        Returns:
            New ThinkingStep
        """
        step = ThinkingStep(
            type=step_type,
            content=content,
            duration_ms=duration_ms,
            tokens=tokens,
        )
        block.add_step(step)
        return step

    async def complete_block(self, block: ThinkingBlock, session: ThinkingSession | None = None) -> None:
        """Mark a thinking block as complete."""
        block.complete()

        # Check if block ended with a tool call - if so, mark as PAUSED instead of COMPLETED
        if block.steps and block.steps[-1].type == ThinkingStepType.TOOL_CALL:
            from app.thinking.models import ThinkingBlockStatus
            block.status = ThinkingBlockStatus.PAUSED_FOR_TOOL

        # Check for critiques to save as lessons
        if block.level in (ThinkingLevel.HIGH, ThinkingLevel.MAX):
            critique_step = next(
                (s for s in block.steps if s.type == ThinkingStepType.CRITIQUE),
                None
            )
            if critique_step:
                try:
                    from app.thinking.memory import get_thinking_memory
                    from app.projects.registry import project_registry
                    
                    # Resolve project root
                    project_root = None
                    if session and session.active_project_name:
                        project = project_registry.get(session.active_project_name)
                        if project and project.path:
                            project_root = project.path

                    # Get project-scoped memory if available
                    memory = get_thinking_memory(project_root)
                    
                    # Use the block's first step as context if available
                    if block.steps and block.steps[0].type == ThinkingStepType.ANALYSIS:
                        context = block.steps[0].content[:200]
                    
                    # Extract tags if present (e.g. hashtags in content)
                    tags = re.findall(r'#(\w+)', critique_step.content)
                    
                    # If hashtags are sparse, perform async AI tagging
                    if len(tags) < 2:
                        asyncio.create_task(
                            self._generate_tags_and_update(
                                context, critique_step.content, session, block, tags
                            )
                        )
                    else:
                        await memory.save_lesson(
                            context=context,
                            critique=critique_step.content,
                            tags=tags,
                            project_id=session.project_id if session else None,
                            metadata={"block_id": block.id, "template": block.template}
                        )
                except Exception as e:
                    print(f"Failed to save critique lesson: {e}")

    async def _generate_tags_and_update(
        self,
        context: str,
        critique: str,
        session: ThinkingSession | None,
        block: ThinkingBlock,
        existing_tags: list[str]
    ) -> None:
        """Background task to generate tags and save the lesson."""
        try:
            from app.thinking.memory import get_thinking_memory
            from app.projects.registry import project_registry
            from app.llm import kiro_provider
            import json

            # Resolve project root
            project_root = None
            if session and session.active_project_name:
                project = project_registry.get(session.active_project_name)
                if project and project.path:
                    project_root = project.path

            memory = get_thinking_memory(project_root)
            
            # If kiro not available, just save with existing tags
            if not await kiro_provider.is_available():
                await memory.save_lesson(
                    context=context,
                    critique=critique,
                    tags=existing_tags,
                    project_id=session.project_id if session else None,
                    metadata={"block_id": block.id, "template": block.template}
                )
                return

            # Ask AI for tags
            prompt = f"""Analyze this critique and generate 3-5 relevant technical tags (e.g., "security", "python", "react", "api").
            
            Context: {context}
            Critique: {critique}
            
            Return ONLY a JSON array of strings. Example: ["security", "auth"]"""

            response = await kiro_provider.generate_short_response(prompt, max_length=200)
            
            try:
                # cleanup potential markdown
                if "```" in response:
                    response = re.search(r'\[.*?\]', response, re.DOTALL).group(0)
                
                new_tags = json.loads(response)
                if isinstance(new_tags, list):
                    # Merge with existing tags (unique)
                    final_tags = list(set(existing_tags + [t.lower() for t in new_tags if isinstance(t, str)]))
                else:
                    final_tags = existing_tags
            except Exception:
                # Fallback to just existing tags
                final_tags = existing_tags

            await memory.save_lesson(
                context=context,
                critique=critique,
                tags=final_tags,
                project_id=session.project_id if session else None,
                metadata={"block_id": block.id, "template": block.template}
            )
            
        except Exception as e:
            print(f"Error in auto-tagging: {e}")
            # Fallback save
            try:
                await memory.save_lesson(
                    context=context,
                    critique=critique,
                    tags=existing_tags,
                    project_id=session.project_id if session else None,
                    metadata={"block_id": block.id, "template": block.template}
                )
            except Exception:
                pass

    def pause_block_for_tool(self, block: ThinkingBlock) -> None:
        """Pause a thinking block for tool execution."""
        from app.thinking.models import ThinkingBlockStatus
        block.status = ThinkingBlockStatus.PAUSED_FOR_TOOL

    def resume_block(self, session: ThinkingSession, block_id: str) -> ThinkingBlock | None:
        """Resume a paused thinking block."""
        from app.thinking.models import ThinkingBlockStatus
        
        # Find block in session
        for block in session.blocks:
            if block.id == block_id:
                if block.status == ThinkingBlockStatus.PAUSED_FOR_TOOL:
                    block.status = ThinkingBlockStatus.RUNNING
                    return block
        return None

    def add_tool_step(
        self,
        block: ThinkingBlock,
        tool_name: str,
        tool_input: dict[str, Any],
        tool_output: str,
        duration_ms: int = 0,
    ) -> None:
        """Add a tool call/result pair as thinking steps."""
        from app.thinking.models import ThinkingStepType as Type
        from app.thinking.models import ThinkingStep

        # Add call step
        call_step = ThinkingStep(
            type=Type.TOOL_CALL,
            content=f"Calling tool: {tool_name}",
            duration_ms=0,
            metadata={"tool_name": tool_name, "input": tool_input}
        )
        block.add_step(call_step)

        # Add result step
        result_step = ThinkingStep(
            type=Type.TOOL_RESULT,
            content=f"Tool output: {tool_output}",
            duration_ms=duration_ms,
            metadata={"tool_name": tool_name}
        )
        block.add_step(result_step)
        
    def resume_with_result(self, session: ThinkingSession, tool_output: str) -> None:
        """Resume a session with a tool result.
        
        This finds the last paused block and adds the tool result to it (or a new linked block).
        For now, we just ensure the session is active.
        """
        # Logic to potentially link blocks would go here
        # Currently we rely on the LLM starting a new block
        pass

    def parse_legacy_content(self, content: str) -> list[ThinkingStep]:
        """Parse legacy XML-style thinking content into steps.

        Args:
            content: Raw thinking content (may contain XML tags)

        Returns:
            List of ThinkingStep objects
        """
        steps = []

        # Try to parse step markers first
        step_matches = list(self.STEP_PATTERN.finditer(content))

        if step_matches:
            for match in step_matches:
                step_type_str = match.group("type").upper()
                step_content = match.group("content").strip()

                # Map to ThinkingStepType
                type_map = {
                    "ANALYSIS": ThinkingStepType.ANALYSIS,
                    "EVALUATION": ThinkingStepType.EVALUATION,
                    "DECISION": ThinkingStepType.DECISION,
                    "VALIDATION": ThinkingStepType.VALIDATION,
                    "RISK": ThinkingStepType.RISK_ASSESSMENT,
                    "IMPLEMENTATION": ThinkingStepType.IMPLEMENTATION,
                    "CRITIQUE": ThinkingStepType.CRITIQUE,
                    "TOOL_CALL": ThinkingStepType.TOOL_CALL,
                    "TOOL_RESULT": ThinkingStepType.TOOL_RESULT,
                }
                step_type = type_map.get(step_type_str, ThinkingStepType.ANALYSIS)

                if step_content:
                    steps.append(ThinkingStep(type=step_type, content=step_content))
        else:
            # No step markers - treat entire content as single analysis step
            clean_content = self.THINKING_START_PATTERN.sub("", content)
            clean_content = self.THINKING_END_PATTERN.sub("", clean_content).strip()

            if clean_content:
                steps.append(ThinkingStep(
                    type=ThinkingStepType.ANALYSIS,
                    content=clean_content,
                ))

        return steps

    def extract_thinking_from_stream(
        self,
        content: str,
    ) -> tuple[str, str | None]:
        """Extract thinking content from a streamed response.

        Args:
            content: Raw content that may contain thinking tags

        Returns:
            Tuple of (clean_content, thinking_content or None)
        """
        thinking_content = None

        # Check for thinking tags
        start_match = self.THINKING_START_PATTERN.search(content)
        end_match = self.THINKING_END_PATTERN.search(content)

        if start_match and end_match and end_match.start() > start_match.end():
            # Complete thinking block found
            thinking_content = content[start_match.end():end_match.start()].strip()
            clean_content = (
                content[:start_match.start()] +
                content[end_match.end():]
            ).strip()
            return clean_content, thinking_content
        elif start_match and not end_match:
            # Thinking block started but not ended
            thinking_content = content[start_match.end():].strip()
            clean_content = content[:start_match.start()].strip()
            return clean_content, thinking_content

        return content, None

    def generate_thinking_prompt(
        self,
        level: ThinkingLevel,
        template: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> str:
        """Generate a thinking prompt for the given level and template.

        Args:
            level: Thinking level to use
            template: Optional template name
            context: Optional context for the prompt

        Returns:
            Thinking prompt string
        """
        if level == ThinkingLevel.OFF:
            return ""

        base_prompts = {
            ThinkingLevel.MINIMAL: (
                "Before responding, briefly consider: Is this request clear? "
                "Any obvious issues?"
            ),
            ThinkingLevel.LOW: (
                "Before responding, analyze the request:\n"
                "1. What is being asked?\n"
                "2. What are the key requirements?\n"
            ),
            ThinkingLevel.MEDIUM: (
                "Before responding, think through this systematically:\n"
                "[ANALYSIS] Break down the problem\n"
                "[TOOL_CALL] Verify assumptions if needed (e.g., check files)\n"
                "[EVALUATION] Consider approaches\n"
                "[DECISION] Choose the best approach\n"
            ),
            ThinkingLevel.HIGH: (
                "Before responding, perform deep analysis:\n"
                "[ANALYSIS] Break down the problem completely\n"
                "[TOOL_CALL] Gather necessary context (read files, grep, etc.)\n"
                "[EVALUATION] Consider multiple approaches with pros/cons\n"
                "[RISK] Identify potential issues and edge cases\n"
                "[DECISION] Select and justify the best approach\n"
                "[VALIDATION] Verify the decision is sound\n"
            ),
            ThinkingLevel.MAX: (
                "Before responding, perform exhaustive analysis:\n"
                "[ANALYSIS] Comprehensively break down all aspects\n"
                "[TOOL_CALL] validate every assumption with ground truth\n"
                "[EVALUATION] Evaluate all possible approaches\n"
                "[RISK] Thoroughly assess risks and edge cases\n"
                "[DECISION] Make a well-justified decision\n"
                "[IMPLEMENTATION] Plan the execution\n"
                "[VALIDATION] Verify completeness and correctness\n"
                "[CRITIQUE] Self-review and identify weaknesses. Use hashtags (e.g., #security, #perf) to tag learned lessons.\n"
            ),
        }

        prompt = base_prompts.get(level, base_prompts[ThinkingLevel.MEDIUM])

        # Add template-specific guidance if provided
        if template:
            from app.thinking.templates import get_template
            template_obj = get_template(template)
            if template_obj:
                prompt += f"\n\nFocus areas for {template}:\n"
                prompt += "\n".join(f"- {focus}" for focus in template_obj.focus_areas)

        # General tool use instruction for levels that support it
        if level in (ThinkingLevel.MEDIUM, ThinkingLevel.HIGH, ThinkingLevel.MAX):
            prompt += (
                "\n\nYou can use tools during thinking to verify facts. "
                "If you need to use a tool:\n"
                "1. Output [TOOL_CALL] to signal intent.\n"
                "2. CLOSE the thinking block with </thinking>.\n"
                "3. Output the standard <tool_call> format.\n"
                "4. After the tool runs, you will receive the result and can start a NEW thinking block to continue analysis."
            )

        return prompt

    async def stream_thinking_events(
        self,
        session: ThinkingSession,
        content_stream: AsyncIterator[str],
    ) -> AsyncIterator[dict[str, Any]]:
        """Process a content stream and yield thinking events.

        Args:
            session: The thinking session
            content_stream: Async iterator of content chunks

        Yields:
            Dict events for SSE streaming
        """
        in_thinking = False
        thinking_buffer = ""
        current_block: ThinkingBlock | None = None
        start_time = time.time()

        async for chunk in content_stream:
            # Check for thinking markers
            if "__THINKING_START__" in chunk or self.THINKING_START_PATTERN.search(chunk):
                in_thinking = True
                current_block = self.start_block(session)
                yield {
                    "type": "thinking_start",
                    "block_id": current_block.id,
                    "level": session.effective_level.value,
                }
                # Remove marker from chunk
                chunk = chunk.replace("__THINKING_START__", "")
                chunk = self.THINKING_START_PATTERN.sub("", chunk)

            if "__THINKING_END__" in chunk or self.THINKING_END_PATTERN.search(chunk):
                in_thinking = False
                # Remove marker from chunk
                chunk = chunk.replace("__THINKING_END__", "")
                chunk = self.THINKING_END_PATTERN.sub("", chunk)

                if current_block and thinking_buffer:
                    if current_block and thinking_buffer:
                        # Parse accumulated thinking content
                        steps = self.parse_legacy_content(thinking_buffer)
                        duration_ms = int((time.time() - start_time) * 1000)

                        for step in steps:
                            step.duration_ms = duration_ms // max(len(steps), 1)
                            current_block.add_step(step)

                        await self.complete_block(current_block, session)

                        yield {
                            "type": "thinking_complete",
                            "block": current_block.to_dict(),
                        }

                thinking_buffer = ""
                current_block = None
                start_time = time.time()

            if in_thinking:
                thinking_buffer += chunk
                # Yield incremental thinking update
                if current_block:
                    yield {
                        "type": "thinking_progress",
                        "block_id": current_block.id,
                        "content": chunk,
                    }
            else:
                # Regular content
                if chunk.strip():
                    yield {
                        "type": "content",
                        "data": chunk,
                    }

        # End of stream check
        if in_thinking and current_block:
            # Stream ended while in thinking block - implies tool call interruption
            # Parse whatever we have in the buffer
            if thinking_buffer:
                steps = self.parse_legacy_content(thinking_buffer)
                for step in steps:
                    current_block.add_step(step)
            
            self.pause_block_for_tool(current_block)
            yield {
                "type": "thinking_paused",
                "block_id": current_block.id,
                "block": current_block.to_dict(),
            }

    def to_json(self, session: ThinkingSession) -> str:
        """Convert a thinking session to JSON string."""
        return json.dumps(session.to_dict(), indent=2)

    def from_json(self, json_str: str) -> ThinkingSession:
        """Create a thinking session from JSON string."""
        data = json.loads(json_str)
        return ThinkingSession.from_dict(data)


    async def record_tool_usage(
        self,
        session: ThinkingSession,
        tool_name: str,
        tool_args: dict[str, Any],
        success: bool,
        output: str,
    ) -> None:
        """Record tool usage in memory if it modifies project state."""
        if not success:
            return

        # List of tools that modify files
        modification_tools = {
            "write_to_file",
            "replace_file_content",
            "multi_replace_file_content",
            "apply_diff",
        }

        if tool_name not in modification_tools:
            return

        # Extract file path
        file_path = tool_args.get("TargetFile") or tool_args.get("path") or tool_args.get("file_path")
        if not file_path:
            # Fallback for old args
            file_path = tool_args.get("target_file")
        
        if not file_path:
            return
            
        description = tool_args.get("Description") or tool_args.get("description") or f"Modified {file_path}"
        
        # Create a context lesson
        try:
            from app.thinking.memory import get_thinking_memory
            from app.projects.registry import project_registry
            
            # Resolve project root
            project_root = None
            if session and session.active_project_name:
                project = project_registry.get(session.active_project_name)
                if project and project.path:
                    project_root = project.path
            
            memory = get_thinking_memory(project_root)
            
            # Context is the action
            context = f"File Modified: {file_path}"
            
            # Critique is the description/goal
            critique = f"Action: {tool_name}\nDescription: {description}\n\nOutcome: {output[:200]}"
            
            # Tags
            tags = ["file_change", "context", tool_name]
            
            # Save synchronously via async helper equivalent if needed, but save_lesson is async
            await memory.save_lesson(
                context=context,
                critique=critique,
                tags=tags,
                project_id=session.project_id,
                metadata={
                    "tool": tool_name,
                    "file_path": file_path,
                    "session_id": session.id,
                    "auto_generated": True
                }
            )
        except Exception as e:
            # Don't fail the tool execution if memory fails
            print(f"Failed to record tool usage context: {e}")

# Global instance for convenience
_default_manager: ThinkingManager | None = None


def get_thinking_manager() -> ThinkingManager:
    """Get the global thinking manager instance."""
    global _default_manager
    if _default_manager is None:
        _default_manager = ThinkingManager()
    return _default_manager
