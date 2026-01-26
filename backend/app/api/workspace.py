"""Workspace management API endpoints."""

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.tools.workspace import workspace_manager, cleanup_kiro_temp_files

router = APIRouter(prefix="/workspace")


@router.get("/stats")
async def get_workspace_stats() -> dict[str, Any]:
    """Get workspace statistics."""
    stats = workspace_manager.get_stats()
    return {
        "workspace_path": str(workspace_manager.workspace_dir),
        **stats.to_dict(),
    }


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
