"""Base agent interface."""

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

import litellm

from app.config import settings
from app.tools import ToolResult, registry as tool_registry

logger = logging.getLogger(__name__)


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

    return '\n'.join(result)


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

    @property
    def id(self) -> str:
        return self.config.id

    @property
    def name(self) -> str:
        return self.config.name

    def get_system_prompt(self, context: dict[str, Any] | None = None) -> str:
        """Get system prompt, optionally with context.

        Automatically detects and injects matching skills based on task/query.
        """
        prompt = self.config.system_prompt

        if context:
            # AUTO-SELECT SKILLS: Check for matching skills based on task/query
            skill_context = self._get_skill_context(context)
            if skill_context:
                prompt += f"\n\n{skill_context}"

            # Inject project context (conventions, patterns, tech stack)
            if "project" in context and context["project"]:
                prompt += f"\n\n{context['project']}\n"

            # Inject workspace path
            if "workspace" in context:
                prompt += f"\n\n## Workspace\nAll file modifications must be in: `{context['workspace']}`\n"

            # Inject memory context (CRITICAL for accuracy)
            if "memory" in context and context["memory"]:
                prompt += f"\n\n## Relevant Context from Memory\n{context['memory']}\n"

            # Inject file context
            if "files" in context:
                prompt += f"\n\n## Files to Work With\n{context['files']}\n"

        return prompt

    def _get_skill_context(self, context: dict[str, Any]) -> str:
        """Find matching skills and generate context to inject.

        Searches for skills based on:
        1. Explicit skill_id in context
        2. Task description triggers
        3. Query/message triggers
        """
        try:
            from app.skills.base import skill_registry
        except ImportError:
            return ""

        matched_skills = []

        # Check for explicit skill
        if "skill_id" in context:
            skill = skill_registry.get(context["skill_id"])
            if skill:
                matched_skills.append(skill)

        # Check task description for triggers
        if "task" in context and context["task"]:
            matches = skill_registry.find_by_trigger(context["task"])
            for skill in matches:
                if skill not in matched_skills:
                    matched_skills.append(skill)

        # Check query/message for triggers
        if "query" in context and context["query"]:
            matches = skill_registry.find_by_trigger(context["query"])
            for skill in matches:
                if skill not in matched_skills:
                    matched_skills.append(skill)

        # Check user message for triggers
        if "user_message" in context and context["user_message"]:
            matches = skill_registry.find_by_trigger(context["user_message"])
            for skill in matches:
                if skill not in matched_skills:
                    matched_skills.append(skill)

        if not matched_skills:
            return ""

        # Generate skill context
        parts = ["## 🎯 Applicable Skills Detected"]
        parts.append("The following skills have been auto-selected based on your task. Follow their guidelines:\n")

        for skill in matched_skills:
            logger.info(f"Auto-selected skill: {skill.id} for agent {self.id}")
            parts.append(f"### {skill.name}")
            parts.append(skill.to_kiro_context())
            parts.append("")  # blank line between skills

        return "\n".join(parts)

    async def chat(
        self,
        messages: list[Message],
        context: dict[str, Any] | None = None,
        model_override: str | None = None,
        temperature_override: float | None = None,
        max_tokens_override: int | None = None,
    ) -> AsyncIterator[str]:
        """Chat with the agent, yielding response chunks.

        Args:
            messages: List of conversation messages
            context: Optional context dict (workspace, memory, files, etc.)
            model_override: Optional model to use instead of agent's default
            temperature_override: Optional temperature to use
            max_tokens_override: Optional max tokens to use
        """
        # Build message list
        api_messages = []

        # System prompt
        system_prompt = self.get_system_prompt(context)
        if system_prompt:
            api_messages.append({"role": "system", "content": system_prompt})

        # Conversation messages
        api_messages.extend([m.to_dict() for m in messages])

        # Use overrides or defaults
        model = model_override or self.config.model
        temperature = temperature_override if temperature_override is not None else self.config.temperature
        max_tokens = max_tokens_override or settings.max_response_tokens

        # Make API call with streaming and timeout
        try:
            async with asyncio.timeout(settings.llm_timeout):
                response = await litellm.acompletion(
                    model=model,
                    messages=api_messages,
                    tools=self._tool_schemas if self._tool_schemas else None,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    stream=True,
                )
        except asyncio.TimeoutError:
            logger.error(f"LLM call timed out after {settings.llm_timeout}s for agent {self.id}")
            yield f"\n\n⚠️ **Request timed out** after {settings.llm_timeout} seconds. The model took too long to respond. Please try again or simplify your request.\n"
            return

        # Collect for tool calls
        full_content = ""
        tool_calls: list[dict] = []
        
        # Buffer for filtering <thinking> and <analysis> blocks
        buffer = ""
        in_hidden_block = False
        hidden_tag = ""  # Which tag we're currently inside

        async for chunk in response:
            delta = chunk.choices[0].delta

            # Stream content (filter out <thinking> and <analysis> blocks)
            if delta.content:
                full_content += delta.content
                buffer += delta.content
                
                # Hidden tags to filter out (thinking shows indicator, analysis is silent)
                hidden_tags = ["thinking", "analysis"]
                
                # Process buffer to filter hidden blocks
                while True:
                    if in_hidden_block:
                        # Look for closing tag
                        end_tag = f"</{hidden_tag}>"
                        end_idx = buffer.find(end_tag)
                        if end_idx != -1:
                            # Discard everything up to and including closing tag
                            buffer = buffer[end_idx + len(end_tag):]
                            # Signal end of thinking block
                            if hidden_tag == "thinking":
                                yield "__THINKING_END__"
                            in_hidden_block = False
                            hidden_tag = ""
                        else:
                            # Still in hidden block, keep buffering (don't yield)
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
                            # Signal start of thinking block
                            if found_tag == "thinking":
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

            # Collect tool calls
            if delta.tool_calls:
                for tc in delta.tool_calls:
                    if tc.index >= len(tool_calls):
                        tool_calls.append({
                            "id": tc.id or "",
                            "type": "function",
                            "function": {"name": "", "arguments": ""},
                        })
                    if tc.id:
                        tool_calls[tc.index]["id"] = tc.id
                    if tc.function:
                        if tc.function.name:
                            tool_calls[tc.index]["function"]["name"] = tc.function.name
                        if tc.function.arguments:
                            tool_calls[tc.index]["function"]["arguments"] += tc.function.arguments

        # Handle tool calls if any
        if tool_calls:
            yield "\n\n"
            for tc in tool_calls:
                tool_name = tc["function"]["name"]
                try:
                    tool_args = json.loads(tc["function"]["arguments"])
                except json.JSONDecodeError:
                    tool_args = {}

                yield f"🔧 **{tool_name}**\n"

                # Execute tool
                result = await tool_registry.execute(tool_name, **tool_args)

                if result.success:
                    yield f"```\n{result.output[:2000]}\n```\n"
                else:
                    yield f"❌ Error: {result.error}\n"

    async def run_tool(self, tool_id: str, **kwargs: Any) -> ToolResult:
        """Run a specific tool."""
        return await tool_registry.execute(tool_id, **kwargs)
