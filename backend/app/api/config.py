"""Configuration API endpoints."""

from pathlib import Path
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from app.config import get_allowed_write_dirs, get_config_dict, settings, update_config
from app.tools import registry as tool_registry
from app.tools.filesystem import FilesystemTool

router = APIRouter(prefix="/config")


class ConfigUpdate(BaseModel):
    """Config update request."""

    default_model: str | None = None
    max_context_tokens: int | None = None
    max_response_tokens: int | None = None
    debug: bool | None = None

    # Filesystem settings
    allowed_write_dirs: str | None = None  # Comma-separated paths

    # Channel settings
    imessage_enabled: bool | None = None
    imessage_allowed_senders: str | None = None

    webex_enabled: bool | None = None
    webex_token: str | None = None
    webex_webhook_secret: str | None = None
    webex_allowed_users: str | None = None
    webex_allowed_rooms: str | None = None

    telegram_enabled: bool | None = None
    telegram_token: str | None = None
    telegram_allowed_users: str | None = None


@router.get("")
async def get_config() -> dict[str, Any]:
    """Get current configuration."""
    config = get_config_dict()

    # Add workspace info
    fs_tool = tool_registry.get("filesystem")
    if fs_tool and isinstance(fs_tool, FilesystemTool):
        config["workspace"] = str(fs_tool.workspace)

    # Add allowed write directories
    config["allowed_write_dirs"] = settings.allowed_write_dirs
    config["all_allowed_dirs"] = [str(d) for d in get_allowed_write_dirs()]

    # Add channel settings
    config["imessage_enabled"] = settings.imessage_enabled
    config["imessage_allowed_senders"] = settings.imessage_allowed_senders

    config["webex_enabled"] = settings.webex_enabled
    config["webex_token"] = settings.webex_token or ""
    config["webex_allowed_rooms"] = settings.webex_allowed_rooms

    config["telegram_enabled"] = settings.telegram_enabled
    config["telegram_token"] = settings.telegram_token or ""
    config["telegram_allowed_users"] = settings.telegram_allowed_users

    return config


@router.put("")
async def set_config(update: ConfigUpdate) -> dict[str, Any]:
    """Update configuration."""
    from app.channels.manager import channel_manager, init_channels
    from app.config import get_channel_config

    updates = update.model_dump(exclude_none=True)

    # Check if channel settings changed
    channel_keys = [
        "imessage_enabled", "imessage_allowed_senders",
        "webex_enabled", "webex_token", "webex_webhook_secret", "webex_allowed_users", "webex_allowed_rooms",
        "telegram_enabled", "telegram_token", "telegram_allowed_users",
    ]
    channel_changed = any(k in updates for k in channel_keys)

    # Apply updates
    update_config(updates)

    # Reinitialize channels if settings changed
    if channel_changed:
        # Stop existing channels
        await channel_manager.stop_all()

        # Clear and reinitialize
        channel_manager._channels.clear()
        channel_config = get_channel_config()
        if channel_config:
            init_channels(channel_config)
            await channel_manager.start_all()

    # Return full config including channel settings
    return await get_config()


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
                    "claude-sonnet-4.5",
                    "claude-haiku-4.5",
                    "claude-opus-4.5",
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


# === Allowed Write Directories ===


class AllowedDirsUpdate(BaseModel):
    """Update allowed write directories."""

    directories: list[str]  # List of directory paths


@router.get("/allowed-dirs")
async def get_allowed_dirs() -> dict[str, Any]:
    """Get directories where writes are allowed."""
    dirs = get_allowed_write_dirs()
    return {
        "workspace": str(settings.workspace_dir),
        "custom_dirs": settings.allowed_write_dirs,
        "all_allowed": [str(d) for d in dirs],
    }


@router.put("/allowed-dirs")
async def set_allowed_dirs(update: AllowedDirsUpdate) -> dict[str, Any]:
    """Set custom allowed write directories.

    These are in addition to the workspace directory.
    Set to empty list to only allow workspace writes.
    """
    # Validate paths exist
    valid_dirs = []
    errors = []
    for dir_str in update.directories:
        path = Path(dir_str).expanduser().resolve()
        if path.exists() and path.is_dir():
            valid_dirs.append(str(path))
        else:
            errors.append(f"Not a valid directory: {dir_str}")

    # Update settings
    settings.allowed_write_dirs = ",".join(valid_dirs)

    return {
        "workspace": str(settings.workspace_dir),
        "custom_dirs": settings.allowed_write_dirs,
        "all_allowed": [str(d) for d in get_allowed_write_dirs()],
        "errors": errors if errors else None,
    }


@router.post("/allowed-dirs/add")
async def add_allowed_dir(path: str) -> dict[str, Any]:
    """Add a directory to allowed write directories."""
    resolved = Path(path).expanduser().resolve()

    if not resolved.exists():
        return {"error": f"Directory does not exist: {path}"}
    if not resolved.is_dir():
        return {"error": f"Not a directory: {path}"}

    # Get current dirs
    current = [d.strip() for d in settings.allowed_write_dirs.split(",") if d.strip()]

    # Add if not already present
    resolved_str = str(resolved)
    if resolved_str not in current:
        current.append(resolved_str)
        settings.allowed_write_dirs = ",".join(current)

    return {
        "added": resolved_str,
        "all_allowed": [str(d) for d in get_allowed_write_dirs()],
    }


@router.delete("/allowed-dirs/remove")
async def remove_allowed_dir(path: str) -> dict[str, Any]:
    """Remove a directory from allowed write directories."""
    resolved = Path(path).expanduser().resolve()
    resolved_str = str(resolved)

    # Get current dirs
    current = [d.strip() for d in settings.allowed_write_dirs.split(",") if d.strip()]

    # Remove if present
    if resolved_str in current:
        current.remove(resolved_str)
        settings.allowed_write_dirs = ",".join(current)
        return {
            "removed": resolved_str,
            "all_allowed": [str(d) for d in get_allowed_write_dirs()],
        }

    return {
        "error": f"Directory not in allowed list: {path}",
        "all_allowed": [str(d) for d in get_allowed_write_dirs()],
    }
