"""Base tool interface and registry."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolResult:
    """Result from a tool execution."""

    success: bool
    output: str
    error: str | None = None
    data: dict[str, Any] | None = None


@dataclass
class ToolParameter:
    """Tool parameter definition."""

    name: str
    type: str  # string, number, boolean, array, object
    description: str
    required: bool = True
    default: Any = None
    enum: list[str] | None = None


@dataclass
class Tool(ABC):
    """Base class for all tools."""

    id: str
    name: str
    description: str
    parameters: list[ToolParameter] = field(default_factory=list)

    @abstractmethod
    async def execute(self, **kwargs: Any) -> ToolResult:
        """Execute the tool with given parameters."""
        pass

    def to_schema(self) -> dict[str, Any]:
        """Convert to JSON schema for LLM function calling."""
        properties = {}
        required = []

        for param in self.parameters:
            prop: dict[str, Any] = {
                "type": param.type,
                "description": param.description,
            }
            if param.enum:
                prop["enum"] = param.enum
            if param.default is not None:
                prop["default"] = param.default

            properties[param.name] = prop

            if param.required:
                required.append(param.name)

        return {
            "type": "function",
            "function": {
                "name": self.id,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }


class ToolRegistry:
    """Registry for available tools."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register a tool."""
        self._tools[tool.id] = tool

    def get(self, tool_id: str) -> Tool | None:
        """Get a tool by ID."""
        return self._tools.get(tool_id)

    def list_all(self) -> list[Tool]:
        """List all registered tools."""
        return list(self._tools.values())

    def get_schemas(self, tool_ids: list[str] | None = None) -> list[dict[str, Any]]:
        """Get JSON schemas for tools."""
        tools = self._tools.values() if tool_ids is None else [
            self._tools[tid] for tid in tool_ids if tid in self._tools
        ]
        return [t.to_schema() for t in tools]

    async def execute(self, tool_id: str, **kwargs: Any) -> ToolResult:
        """Execute a tool by ID."""
        tool = self._tools.get(tool_id)
        if not tool:
            return ToolResult(success=False, output="", error=f"Tool not found: {tool_id}")
        try:
            return await tool.execute(**kwargs)
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))


# Global registry
registry = ToolRegistry()
