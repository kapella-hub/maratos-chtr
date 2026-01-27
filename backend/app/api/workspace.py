"""Workspace management API endpoints."""

import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.tools.workspace import workspace_manager, cleanup_kiro_temp_files
from app.config import settings

router = APIRouter(prefix="/workspace")


@router.get("/stats")
async def get_workspace_stats() -> dict[str, Any]:
    """Get workspace statistics."""
    stats = workspace_manager.get_stats()
    return {
        "workspace_path": str(workspace_manager.workspace_dir),
        **stats.to_dict(),
    }


class DirectoryEntry(BaseModel):
    """A directory or file entry."""
    name: str
    path: str
    is_dir: bool
    is_git: bool = False
    size: int | None = None
    modified: float | None = None


@router.get("/browse")
async def browse_directory(
    path: str = Query(default="", description="Path to browse (relative to allowed roots or absolute)"),
    show_files: bool = Query(default=False, description="Include files in listing"),
) -> dict[str, Any]:
    """Browse directories for project selection.

    Allows browsing:
    - The maratos workspace directory
    - User's home directory projects
    - Absolute paths (with validation)
    """
    # Determine the path to browse
    if not path or path == "":
        # Return list of root locations
        home = Path.home()
        workspace = Path(settings.workspace)

        roots = []

        # Add workspace
        if workspace.exists():
            roots.append({
                "name": "Maratos Workspace",
                "path": str(workspace),
                "is_dir": True,
                "is_git": False,
            })

        # Add common project directories
        common_dirs = [
            home / "Projects",
            home / "projects",
            home / "Code",
            home / "code",
            home / "Development",
            home / "dev",
            home / "repos",
            home / "src",
        ]

        for d in common_dirs:
            if d.exists() and d.is_dir():
                roots.append({
                    "name": d.name,
                    "path": str(d),
                    "is_dir": True,
                    "is_git": (d / ".git").exists(),
                })

        # Add home directory
        roots.append({
            "name": "Home Directory",
            "path": str(home),
            "is_dir": True,
            "is_git": False,
        })

        return {
            "current_path": "",
            "parent_path": None,
            "entries": roots,
            "is_root": True,
        }

    # Expand user home
    browse_path = Path(path).expanduser()

    # Validate path exists
    if not browse_path.exists():
        raise HTTPException(status_code=404, detail=f"Path not found: {path}")

    if not browse_path.is_dir():
        raise HTTPException(status_code=400, detail=f"Not a directory: {path}")

    # Security: prevent browsing sensitive system directories
    blocked_prefixes = ["/etc", "/var", "/usr", "/bin", "/sbin", "/System", "/Library"]
    path_str = str(browse_path)
    if any(path_str.startswith(p) for p in blocked_prefixes):
        raise HTTPException(status_code=403, detail="Access to system directories is not allowed")

    entries = []
    try:
        for entry in sorted(browse_path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            # Skip hidden files/dirs unless in workspace
            if entry.name.startswith('.') and entry.name not in ['.git']:
                continue

            if entry.is_dir() or show_files:
                is_git = (entry / ".git").exists() if entry.is_dir() else False

                entry_data = {
                    "name": entry.name,
                    "path": str(entry),
                    "is_dir": entry.is_dir(),
                    "is_git": is_git,
                }

                if not entry.is_dir():
                    try:
                        stat = entry.stat()
                        entry_data["size"] = stat.st_size
                        entry_data["modified"] = stat.st_mtime
                    except OSError:
                        pass

                entries.append(entry_data)
    except PermissionError:
        raise HTTPException(status_code=403, detail=f"Permission denied: {path}")

    # Calculate parent path
    parent = browse_path.parent
    parent_path = str(parent) if parent != browse_path else None

    return {
        "current_path": str(browse_path),
        "parent_path": parent_path,
        "entries": entries,
        "is_root": False,
        "is_git": (browse_path / ".git").exists(),
    }


@router.get("/projects")
async def list_workspace_projects() -> list[dict[str, Any]]:
    """List all projects in the workspace directory."""
    workspace = Path(settings.workspace)

    if not workspace.exists():
        return []

    projects = []
    for entry in sorted(workspace.iterdir(), key=lambda x: x.name.lower()):
        if entry.is_dir() and not entry.name.startswith('.'):
            is_git = (entry / ".git").exists()

            # Try to get git info
            git_info = {}
            if is_git:
                try:
                    # Get current branch
                    head_file = entry / ".git" / "HEAD"
                    if head_file.exists():
                        head_content = head_file.read_text().strip()
                        if head_content.startswith("ref: refs/heads/"):
                            git_info["branch"] = head_content.replace("ref: refs/heads/", "")
                except Exception:
                    pass

            # Count files
            file_count = 0
            try:
                for _ in entry.rglob("*"):
                    file_count += 1
                    if file_count > 1000:  # Cap for performance
                        break
            except Exception:
                pass

            projects.append({
                "name": entry.name,
                "path": str(entry),
                "is_git": is_git,
                "git_info": git_info if git_info else None,
                "file_count": file_count if file_count <= 1000 else "1000+",
                "modified": entry.stat().st_mtime,
            })

    return projects


class CleanupRequest(BaseModel):
    """Configuration for cleanup operation."""
    max_age_days: int = 30
    cleanup_temp: bool = True
    cleanup_old: bool = True
    cleanup_empty: bool = True
    cleanup_kiro_temp: bool = True


@router.post("/cleanup")
async def cleanup_workspace(request: CleanupRequest) -> dict[str, Any]:
    """Perform workspace cleanup.

    Cleans up:
    - Temporary files (*.tmp, __pycache__, etc.)
    - Old files (older than max_age_days)
    - Empty directories
    - Kiro CLI temp files in /tmp
    """
    results = workspace_manager.full_cleanup(
        max_age_days=request.max_age_days,
        cleanup_temp=request.cleanup_temp,
        cleanup_old=request.cleanup_old,
        cleanup_empty=request.cleanup_empty,
    )

    if request.cleanup_kiro_temp:
        kiro_deleted = cleanup_kiro_temp_files()
        results["kiro_temp_files"] = {"files_deleted": kiro_deleted}

    return results


@router.post("/cleanup/temp")
async def cleanup_temp_files() -> dict[str, Any]:
    """Clean up temporary files only."""
    result = workspace_manager.cleanup_temp_files()
    return result.to_dict()


@router.post("/cleanup/old")
async def cleanup_old_files(max_age_days: int = 30) -> dict[str, Any]:
    """Clean up files older than specified days."""
    result = workspace_manager.cleanup_old_files(max_age_days)
    return result.to_dict()


@router.post("/cleanup/empty")
async def cleanup_empty_dirs() -> dict[str, Any]:
    """Clean up empty directories."""
    result = workspace_manager.cleanup_empty_dirs()
    return result.to_dict()


@router.post("/cleanup/kiro-temp")
async def cleanup_kiro_temp() -> dict[str, int]:
    """Clean up Kiro CLI temporary files."""
    deleted = cleanup_kiro_temp_files()
    return {"files_deleted": deleted}


@router.get("/large-files")
async def get_large_files(min_size_mb: float = 10) -> list[dict[str, Any]]:
    """Find large files in workspace."""
    return workspace_manager.get_large_files(min_size_mb)


@router.post("/archive/{project_name}")
async def archive_project(project_name: str) -> dict[str, Any]:
    """Archive a project directory to a zip file."""
    archive_path = workspace_manager.archive_project(project_name)
    if archive_path is None:
        raise HTTPException(status_code=404, detail=f"Project not found: {project_name}")

    return {
        "project": project_name,
        "archive_path": str(archive_path),
        "archive_size_mb": round(archive_path.stat().st_size / (1024 * 1024), 2),
    }
