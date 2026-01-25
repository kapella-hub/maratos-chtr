"""Configuration API endpoints."""

from pathlib import Path
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from app.config import get_config_dict, settings, update_config
from app.tools import registry as tool_registry
from app.tools.filesystem import FilesystemTool

router = APIRouter(prefix="/config")


class ConfigUpdate(BaseModel):
    """Config update request."""

    default_model: str | None = None
    max_context_tokens: int | None = None
    max_response_tokens: int | None = None
    debug: bool | None = None


@router.get("")
async def get_config() -> dict[str, Any]:
    """Get current configuration."""
    config = get_config_dict()
    
    # Add workspace info
    fs_tool = tool_registry.get("filesystem")
    if fs_tool and isinstance(fs_tool, FilesystemTool):
        config["workspace"] = str(fs_tool.workspace)
    
    return config


@router.put("")
async def set_config(update: ConfigUpdate) -> dict[str, Any]:
    """Update configuration."""
    updates = update.model_dump(exclude_none=True)
    update_config(updates)
    return get_config_dict()


@router.get("/schema")
async def get_schema() -> dict[str, Any]:
    """Get config schema for UI generation."""
    return {
        "properties": {
            "default_model": {
                "type": "string",
                "title": "Default Model",
                "description": "Default LLM model to use",
                "enum": [
                    "claude-sonnet-4-20250514",
                    "claude-3-5-haiku-20241022",
                    "claude-opus-4-20250514",
                    "gpt-4o",
                    "gpt-4o-mini",
                ],
            },
            "max_context_tokens": {
                "type": "integer",
                "title": "Max Context Tokens",
                "description": "Maximum tokens in context window",
                "minimum": 1000,
                "maximum": 200000,
            },
            "max_response_tokens": {
                "type": "integer",
                "title": "Max Response Tokens",
                "description": "Maximum tokens in response",
                "minimum": 100,
                "maximum": 16000,
            },
            "debug": {
                "type": "boolean",
                "title": "Debug Mode",
                "description": "Enable debug logging",
            },
        },
    }


@router.get("/tools")
async def list_tools() -> list[dict[str, Any]]:
    """List all available tools."""
    return [
        {
            "id": tool.id,
            "name": tool.name,
            "description": tool.description,
            "parameters": [
                {
                    "name": p.name,
                    "type": p.type,
                    "description": p.description,
                    "required": p.required,
                }
                for p in tool.parameters
            ],
        }
        for tool in tool_registry.list_all()
    ]
