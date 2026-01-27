"""Configuration API endpoints."""

import httpx
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import get_allowed_write_dirs, get_config_dict, settings, update_config

logger = logging.getLogger(__name__)
from app.tools import registry as tool_registry
from app.tools.filesystem import FilesystemTool

router = APIRouter(prefix="/config")


class ConfigUpdate(BaseModel):
    """Config update request."""

    default_model: str | None = None
    thinking_level: str | None = None
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

    # Git settings
    git_auto_commit: bool | None = None
    git_push_to_remote: bool | None = None
    git_create_pr: bool | None = None
    git_default_branch: str | None = None
    git_commit_prefix: str | None = None
    git_remote_name: str | None = None

    # GitLab integration
    gitlab_url: str | None = None
    gitlab_token: str | None = None
    gitlab_namespace: str | None = None
    gitlab_skip_ssl: bool | None = None


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

    # Git settings
    config["git_auto_commit"] = settings.git_auto_commit
    config["git_push_to_remote"] = settings.git_push_to_remote
    config["git_create_pr"] = settings.git_create_pr
    config["git_default_branch"] = settings.git_default_branch
    config["git_commit_prefix"] = settings.git_commit_prefix
    config["git_remote_name"] = settings.git_remote_name

    # GitLab integration
    config["gitlab_url"] = settings.gitlab_url
    config["gitlab_token"] = "***" if settings.gitlab_token else ""  # Don't expose full token
    config["gitlab_namespace"] = settings.gitlab_namespace
    config["gitlab_skip_ssl"] = settings.gitlab_skip_ssl
    config["gitlab_configured"] = bool(settings.gitlab_url and settings.gitlab_token)

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
            "thinking_level": {
                "type": "string",
                "title": "Thinking Level",
                "description": "Controls depth of analysis before code execution",
                "enum": ["off", "minimal", "low", "medium", "high", "max"],
                "enumLabels": {
                    "off": "Off - Direct execution",
                    "minimal": "Minimal - Quick sanity check",
                    "low": "Low - Brief analysis",
                    "medium": "Medium - Structured analysis",
                    "high": "High - Deep analysis",
                    "max": "Max - Exhaustive analysis",
                },
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
        raise HTTPException(status_code=400, detail=f"Directory does not exist: {path}")
    if not resolved.is_dir():
        raise HTTPException(status_code=400, detail=f"Not a directory: {path}")

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
    if resolved_str not in current:
        raise HTTPException(
            status_code=404,
            detail=f"Directory not in allowed list: {path}"
        )

    current.remove(resolved_str)
    settings.allowed_write_dirs = ",".join(current)
    return {
        "removed": resolved_str,
        "all_allowed": [str(d) for d in get_allowed_write_dirs()],
    }


# === Directory Browser ===


class BrowseRequest(BaseModel):
    """Request to browse a directory."""
    path: str = "~"


class DirectoryEntry(BaseModel):
    """A directory entry."""
    name: str
    path: str
    is_dir: bool
    is_project: bool = False  # Has package.json, pyproject.toml, etc.
    is_git: bool = False  # Has .git directory (alias for compatibility)


class BrowseResponse(BaseModel):
    """Response from directory browse."""
    current_path: str
    parent_path: str | None
    entries: list[DirectoryEntry]


@router.post("/browse")
async def browse_directory(request: BrowseRequest) -> BrowseResponse:
    """Browse a directory to help users select project folders.

    Returns directories only (not files) for folder selection.
    """
    path = Path(request.path).expanduser().resolve()

    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Path not found: {request.path}")
    if not path.is_dir():
        raise HTTPException(status_code=400, detail=f"Not a directory: {request.path}")

    # Get parent path (if not root)
    parent = path.parent if path != path.parent else None

    # Project indicators
    project_markers = {
        "package.json", "pyproject.toml", "Cargo.toml", "go.mod",
        "pom.xml", "build.gradle", "Gemfile", "composer.json",
        "mix.exs", ".git"
    }

    entries = []
    try:
        for item in sorted(path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            # Skip hidden files/dirs except .git
            if item.name.startswith('.') and item.name != '.git':
                continue

            # Only include directories
            if item.is_dir():
                # Check if this is a project directory
                is_project = any((item / marker).exists() for marker in project_markers)
                is_git = (item / ".git").exists()

                entries.append(DirectoryEntry(
                    name=item.name,
                    path=str(item),
                    is_dir=True,
                    is_project=is_project,
                    is_git=is_git,
                ))
    except PermissionError:
        raise HTTPException(status_code=403, detail=f"Permission denied: {request.path}")

    return BrowseResponse(
        current_path=str(path),
        parent_path=str(parent) if parent else None,
        entries=entries,
    )


# === GitLab Integration ===


class GitLabCreateProjectRequest(BaseModel):
    """Request to create a new GitLab project."""
    name: str  # Project name (slug)
    description: str = ""
    namespace: str | None = None  # Override default namespace
    visibility: str = "private"  # private, internal, or public
    initialize_with_readme: bool = True


class GitLabProjectResponse(BaseModel):
    """Response from GitLab project creation."""
    id: int
    name: str
    path: str
    path_with_namespace: str
    ssh_url_to_repo: str
    http_url_to_repo: str
    web_url: str


@router.post("/gitlab/test")
async def test_gitlab_connection() -> dict[str, Any]:
    """Test GitLab connection with current settings."""
    if not settings.gitlab_url or not settings.gitlab_token:
        raise HTTPException(status_code=400, detail="GitLab not configured. Set URL and token in settings.")

    try:
        async with httpx.AsyncClient(verify=not settings.gitlab_skip_ssl) as client:
            response = await client.get(
                f"{settings.gitlab_url.rstrip('/')}/api/v4/user",
                headers={"PRIVATE-TOKEN": settings.gitlab_token},
                timeout=10.0,
            )

            if response.status_code == 200:
                user = response.json()
                return {
                    "status": "connected",
                    "user": user.get("username"),
                    "name": user.get("name"),
                    "gitlab_url": settings.gitlab_url,
                }
            elif response.status_code == 401:
                raise HTTPException(status_code=401, detail="Invalid GitLab token")
            else:
                raise HTTPException(status_code=response.status_code, detail=f"GitLab API error: {response.text}")

    except httpx.RequestError as e:
        raise HTTPException(status_code=500, detail=f"Cannot connect to GitLab: {str(e)}")


@router.get("/gitlab/namespaces")
async def list_gitlab_namespaces() -> list[dict[str, Any]]:
    """List available GitLab namespaces (groups) for the authenticated user."""
    if not settings.gitlab_url or not settings.gitlab_token:
        raise HTTPException(status_code=400, detail="GitLab not configured")

    try:
        async with httpx.AsyncClient(verify=not settings.gitlab_skip_ssl) as client:
            # Get user's groups
            response = await client.get(
                f"{settings.gitlab_url.rstrip('/')}/api/v4/groups",
                headers={"PRIVATE-TOKEN": settings.gitlab_token},
                params={"min_access_level": 30},  # Developer access or higher
                timeout=10.0,
            )

            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail="Failed to fetch namespaces")

            groups = response.json()
            return [
                {
                    "id": g["id"],
                    "name": g["name"],
                    "path": g["full_path"],
                    "web_url": g["web_url"],
                }
                for g in groups
            ]

    except httpx.RequestError as e:
        raise HTTPException(status_code=500, detail=f"GitLab API error: {str(e)}")


@router.post("/gitlab/projects")
async def create_gitlab_project(request: GitLabCreateProjectRequest) -> GitLabProjectResponse:
    """Create a new GitLab project."""
    if not settings.gitlab_url or not settings.gitlab_token:
        raise HTTPException(status_code=400, detail="GitLab not configured. Set URL and token in settings.")

    namespace = request.namespace or settings.gitlab_namespace
    if not namespace:
        raise HTTPException(status_code=400, detail="No namespace specified and no default configured")

    try:
        async with httpx.AsyncClient(verify=not settings.gitlab_skip_ssl) as client:
            # First, get the namespace ID
            namespace_response = await client.get(
                f"{settings.gitlab_url.rstrip('/')}/api/v4/groups/{namespace.replace('/', '%2F')}",
                headers={"PRIVATE-TOKEN": settings.gitlab_token},
                timeout=10.0,
            )

            if namespace_response.status_code != 200:
                raise HTTPException(
                    status_code=404,
                    detail=f"Namespace '{namespace}' not found or no access"
                )

            namespace_id = namespace_response.json()["id"]

            # Create the project
            project_data = {
                "name": request.name,
                "path": request.name.lower().replace(" ", "-").replace("_", "-"),
                "namespace_id": namespace_id,
                "description": request.description,
                "visibility": request.visibility,
                "initialize_with_readme": request.initialize_with_readme,
            }

            response = await client.post(
                f"{settings.gitlab_url.rstrip('/')}/api/v4/projects",
                headers={"PRIVATE-TOKEN": settings.gitlab_token},
                json=project_data,
                timeout=30.0,
            )

            if response.status_code == 201:
                project = response.json()
                logger.info(f"Created GitLab project: {project['path_with_namespace']}")
                return GitLabProjectResponse(
                    id=project["id"],
                    name=project["name"],
                    path=project["path"],
                    path_with_namespace=project["path_with_namespace"],
                    ssh_url_to_repo=project["ssh_url_to_repo"],
                    http_url_to_repo=project["http_url_to_repo"],
                    web_url=project["web_url"],
                )
            elif response.status_code == 400:
                error = response.json()
                raise HTTPException(status_code=400, detail=error.get("message", "Failed to create project"))
            else:
                raise HTTPException(status_code=response.status_code, detail=f"GitLab error: {response.text}")

    except httpx.RequestError as e:
        raise HTTPException(status_code=500, detail=f"GitLab API error: {str(e)}")
