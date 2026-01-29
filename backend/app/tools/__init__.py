"""Tool system for MaratOS."""

from app.tools.base import Tool, ToolResult, registry
from app.tools.executor import tool_executor, ToolExecutor, ToolMetrics, ToolRateLimit
from app.tools.interpreter import (
    ToolInterpreter,
    ToolInvocation,
    ToolExecutionResult,
    ToolPolicy,
    InterpreterContext,
    parse_tool_blocks,
    has_tool_calls,
    strip_tool_blocks,
    format_tool_results_for_llm,
)
from app.tools.filesystem import FilesystemTool
from app.tools.shell import ShellTool
from app.tools.web import WebSearchTool, WebFetchTool
from app.tools.kiro import KiroTool
from app.tools.orchestrate import OrchestrateTool
from app.tools.sessions import SessionsTool
from app.tools.canvas import CanvasTool
from app.tools.routing import RoutingTool
from app.tools.market_data import MarketDataTool, QuoteTool

__all__ = [
    "Tool",
    "ToolResult",
    "registry",
    "tool_executor",
    "ToolExecutor",
    "ToolMetrics",
    "ToolRateLimit",
    "ToolInterpreter",
    "ToolInvocation",
    "ToolExecutionResult",
    "ToolPolicy",
    "InterpreterContext",
    "parse_tool_blocks",
    "has_tool_calls",
    "strip_tool_blocks",
    "format_tool_results_for_llm",
    "FilesystemTool",
    "ShellTool",
    "WebSearchTool",
    "WebFetchTool",
    "KiroTool",
    "OrchestrateTool",
    "SessionsTool",
    "CanvasTool",
    "RoutingTool",
    "MarketDataTool",
    "QuoteTool",
]
