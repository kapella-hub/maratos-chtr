"""Base agent interface."""

import json
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

import litellm

from app.config import settings
from app.tools import ToolResult, registry as tool_registry


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
        """Get system prompt, optionally with context."""
        return self.config.system_prompt

    async def chat(
        self,
        messages: list[Message],
        context: dict[str, Any] | None = None,
    ) -> AsyncIterator[str]:
        """Chat with the agent, yielding response chunks."""
        # Build message list
        api_messages = []

        # System prompt
        system_prompt = self.get_system_prompt(context)
        if system_prompt:
            api_messages.append({"role": "system", "content": system_prompt})

        # Conversation messages
        api_messages.extend([m.to_dict() for m in messages])

        # Make API call with streaming
        response = await litellm.acompletion(
            model=self.config.model,
            messages=api_messages,
            tools=self._tool_schemas if self._tool_schemas else None,
            temperature=self.config.temperature,
            max_tokens=settings.max_response_tokens,
            stream=True,
        )

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
                
                # Hidden tags to filter out
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
