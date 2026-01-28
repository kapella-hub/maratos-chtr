"""Tools API endpoints."""

import logging
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.tools import registry
from app.tools.executor import tool_executor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tools", tags=["tools"])


class ToolInfo(BaseModel):
    """Tool information."""

    id: str
    name: str
    description: str
    parameters: list[dict[str, Any]]


class ToolMetricsResponse(BaseModel):
    """Tool metrics response."""

    tool_id: str
    total_calls: int
    successful_calls: int
    failed_calls: int
    success_rate: float
    avg_duration_ms: float
    last_called_at: str | None


@router.get("")
async def list_tools() -> list[ToolInfo]:
    """List all registered tools."""
    tools = registry.list_all()
    return [
        ToolInfo(
            id=t.id,
            name=t.name,
            description=t.description,
            parameters=[
                {
                    "name": p.name,
                    "type": p.type,
                    "description": p.description,
                    "required": p.required,
                }
                for p in t.parameters
            ],
        )
        for t in tools
    ]


@router.get("/metrics")
async def get_tool_metrics(
    tool_id: str | None = Query(default=None),
) -> dict[str, Any]:
    """Get tool execution metrics."""
    return tool_executor.get_metrics(tool_id)


@router.get("/rate-limits")
async def get_rate_limits() -> dict[str, Any]:
    """Get rate limit status for all tools with limits."""
    result = {}
    for tool in registry.list_all():
        status = tool_executor.get_rate_limit_status(tool.id)
        if status.get("limited"):
            result[tool.id] = status
    return result


@router.get("/{tool_id}")
async def get_tool(tool_id: str) -> ToolInfo:
    """Get a specific tool by ID."""
    tool = registry.get(tool_id)
    if not tool:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Tool not found: {tool_id}")

    return ToolInfo(
        id=tool.id,
        name=tool.name,
        description=tool.description,
        parameters=[
            {
                "name": p.name,
                "type": p.type,
                "description": p.description,
                "required": p.required,
            }
            for p in tool.parameters
        ],
    )


@router.get("/{tool_id}/metrics")
async def get_single_tool_metrics(tool_id: str) -> dict[str, Any]:
    """Get metrics for a specific tool."""
    return tool_executor.get_metrics(tool_id)


@router.get("/{tool_id}/rate-limit")
async def get_tool_rate_limit(tool_id: str) -> dict[str, Any]:
    """Get rate limit status for a specific tool."""
    return tool_executor.get_rate_limit_status(tool_id)
