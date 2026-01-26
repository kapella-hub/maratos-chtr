"""API endpoints for autonomous development mode."""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.autonomous.models import (
    ProjectPlan,
    ProjectConfig,
    ProjectStatus,
    AutonomousTaskStatus,
)
from app.autonomous.orchestrator import Orchestrator
from app.autonomous.project_manager import project_manager
from app.autonomous.model_selector import (
    get_available_models_info,
    refresh_available_models,
    model_selector,
)
from app.config import settings
from app.database import (
    AutonomousProject as DBProject,
    AutonomousTask as DBTask,
    get_db,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/autonomous", tags=["autonomous"])


class StartProjectRequest(BaseModel):
    """Request to start a new autonomous project."""
    name: str
    prompt: str
    workspace_path: str | None = None
    auto_commit: bool = True
    push_to_remote: bool = False
    create_pr: bool = False
    pr_base_branch: str = "main"
    max_runtime_hours: float = 8.0
    max_total_iterations: int = 50
    parallel_tasks: int = 3
    # Git repository options
    git_mode: str = "existing"  # "new", "existing", or "none"
    git_remote_url: str | None = None  # Remote URL for push
    git_init_repo: bool = True  # Initialize git repo if not exists


class ProjectResponse(BaseModel):
    """Project response."""
    id: str
    name: str
    original_prompt: str
    workspace_path: str
    status: str
    progress: float
    tasks_completed: int
    tasks_failed: int
    tasks_pending: int
    total_iterations: int
    branch_name: str | None
    pr_url: str | None
    error: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class TaskResponse(BaseModel):
    """Task response."""
    id: str
    title: str
    description: str
    agent_type: str
    status: str
    depends_on: list[str]
    quality_gates: list[dict]
    current_attempt: int
    max_attempts: int
    priority: int
    target_files: list[str]
    final_commit_sha: str | None
    error: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class ProjectDetailResponse(BaseModel):
    """Detailed project response with tasks."""
    project: ProjectResponse
    tasks: list[TaskResponse]


@router.post("/start")
async def start_project(
    request: StartProjectRequest,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Start a new autonomous development project."""
    # Determine workspace path
    if request.workspace_path:
        workspace = Path(request.workspace_path)
    else:
        # Use default workspace under maratos-workspace
        workspace = Path(settings.workspace) / f"auto-{request.name.lower().replace(' ', '-')}"

    workspace.mkdir(parents=True, exist_ok=True)

    # Create config
    config = ProjectConfig(
        auto_commit=request.auto_commit,
        push_to_remote=request.push_to_remote,
        create_pr=request.create_pr,
        pr_base_branch=request.pr_base_branch,
        max_runtime_hours=request.max_runtime_hours,
        max_total_iterations=request.max_total_iterations,
        parallel_tasks=request.parallel_tasks,
    )

    # Create project
    project = await project_manager.create_project(
        name=request.name,
        prompt=request.prompt,
        workspace_path=workspace,
        config=config,
    )

    # Save to database
    db_project = DBProject(
        id=project.id,
        name=project.name,
        original_prompt=project.original_prompt,
        workspace_path=project.workspace_path,
        status=project.status.value,
        config=project.config.to_dict(),
    )
    db.add(db_project)
    await db.commit()

    async def generate():
        """Generate SSE stream."""
        orchestrator = Orchestrator(project)

        # Register orchestrator so it can be cancelled via API
        project_manager.register_orchestrator(project.id, orchestrator)

        try:
            async for event in orchestrator.start():
                # Check if cancelled
                if orchestrator._cancelled:
                    logger.info(f"Project {project.id} cancelled, stopping stream")
                    break

                yield event.to_sse()

                # Update database periodically
                if event.type.value in ("task_completed", "task_failed", "project_completed", "project_failed"):
                    await _save_project_state(db, project)

        except asyncio.CancelledError:
            logger.info(f"Project {project.id} stream cancelled")
            orchestrator.cancel()

        except Exception as e:
            logger.error(f"Project {project.id} error: {e}", exc_info=True)
            yield f'data: {{"type": "error", "error": "{str(e)}"}}\n\n'

        finally:
            # Final save
            await _save_project_state(db, project)
            project_manager.unregister_orchestrator(project.id)

        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Project-ID": project.id,
        },
    )


@router.get("/projects")
async def list_projects(
    status: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> list[ProjectResponse]:
    """List autonomous projects."""
    query = select(DBProject).order_by(DBProject.created_at.desc()).limit(limit)

    if status:
        query = query.where(DBProject.status == status)

    result = await db.execute(query)
    projects = result.scalars().all()

    return [
        ProjectResponse(
            id=p.id,
            name=p.name,
            original_prompt=p.original_prompt[:200],
            workspace_path=p.workspace_path,
            status=p.status,
            progress=_calculate_progress(p.id),
            tasks_completed=0,
            tasks_failed=0,
            tasks_pending=0,
            total_iterations=p.total_iterations,
            branch_name=p.branch_name,
            pr_url=p.pr_url,
            error=p.error,
            created_at=p.created_at,
            started_at=p.started_at,
            completed_at=p.completed_at,
        )
        for p in projects
    ]


@router.get("/projects/{project_id}")
async def get_project(
    project_id: str,
    db: AsyncSession = Depends(get_db),
) -> ProjectDetailResponse:
    """Get project details with tasks."""
    result = await db.execute(
        select(DBProject).where(DBProject.id == project_id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Get tasks
    result = await db.execute(
        select(DBTask)
        .where(DBTask.project_id == project_id)
        .order_by(DBTask.priority.desc(), DBTask.created_at)
    )
    tasks = result.scalars().all()

    completed = len([t for t in tasks if t.status == "completed"])
    failed = len([t for t in tasks if t.status == "failed"])
    pending = len([t for t in tasks if t.status not in ("completed", "failed", "skipped")])

    return ProjectDetailResponse(
        project=ProjectResponse(
            id=project.id,
            name=project.name,
            original_prompt=project.original_prompt,
            workspace_path=project.workspace_path,
            status=project.status,
            progress=completed / len(tasks) if tasks else 0,
            tasks_completed=completed,
            tasks_failed=failed,
            tasks_pending=pending,
            total_iterations=project.total_iterations,
            branch_name=project.branch_name,
            pr_url=project.pr_url,
            error=project.error,
            created_at=project.created_at,
            started_at=project.started_at,
            completed_at=project.completed_at,
        ),
        tasks=[
            TaskResponse(
                id=t.id,
                title=t.title,
                description=t.description[:500],
                agent_type=t.agent_type,
                status=t.status,
                depends_on=t.depends_on or [],
                quality_gates=t.quality_gates or [],
                current_attempt=len(t.iterations or []),
                max_attempts=t.max_attempts,
                priority=t.priority,
                target_files=t.target_files or [],
                final_commit_sha=t.final_commit_sha,
                error=t.error,
                created_at=t.created_at,
                started_at=t.started_at,
                completed_at=t.completed_at,
            )
            for t in tasks
        ],
    )


@router.post("/projects/{project_id}/pause")
async def pause_project(
    project_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Pause a running project."""
    project = project_manager.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found in manager")

    if await project_manager.pause_project(project_id):
        # Update DB
        result = await db.execute(
            select(DBProject).where(DBProject.id == project_id)
        )
        db_project = result.scalar_one_or_none()
        if db_project:
            db_project.status = "paused"
            db_project.paused_at = datetime.now()
            await db.commit()

        return {"status": "paused", "project_id": project_id}

    raise HTTPException(status_code=400, detail="Cannot pause project in current state")


@router.post("/projects/{project_id}/resume")
async def resume_project(
    project_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Resume a paused project."""
    project = project_manager.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found in manager")

    if await project_manager.resume_project(project_id):
        # Update DB
        result = await db.execute(
            select(DBProject).where(DBProject.id == project_id)
        )
        db_project = result.scalar_one_or_none()
        if db_project:
            db_project.status = "in_progress"
            db_project.paused_at = None
            await db.commit()

        return {"status": "resumed", "project_id": project_id}

    raise HTTPException(status_code=400, detail="Cannot resume project in current state")


@router.post("/projects/{project_id}/cancel")
async def cancel_project(
    project_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Cancel a project."""
    # Try to cancel in memory (orchestrator + project manager)
    cancelled_in_memory = await project_manager.cancel_project(project_id)

    # Also update DB regardless of in-memory status
    result = await db.execute(
        select(DBProject).where(DBProject.id == project_id)
    )
    db_project = result.scalar_one_or_none()

    if db_project:
        db_project.status = "cancelled"
        db_project.completed_at = datetime.now()
        await db.commit()
        logger.info(f"Cancelled project in DB: {project_id}")
        return {"status": "cancelled", "project_id": project_id}

    if cancelled_in_memory:
        return {"status": "cancelled", "project_id": project_id}

    raise HTTPException(status_code=404, detail="Project not found")


@router.post("/projects/{project_id}/tasks/{task_id}/retry")
async def retry_task(
    project_id: str,
    task_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Retry a failed task."""
    project = project_manager.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    task = project.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.status != AutonomousTaskStatus.FAILED:
        raise HTTPException(status_code=400, detail="Task is not in failed state")

    # Reset task for retry
    task.status = AutonomousTaskStatus.READY
    task.error = None
    task.iterations = []

    # Update DB
    result = await db.execute(
        select(DBTask).where(DBTask.id == task_id)
    )
    db_task = result.scalar_one_or_none()
    if db_task:
        db_task.status = "ready"
        db_task.error = None
        db_task.iterations = []
        await db.commit()

    return {"status": "retrying", "task_id": task_id}


@router.get("/stats")
async def get_stats(
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get autonomous system statistics."""
    manager_stats = project_manager.get_stats()

    # Get DB counts
    result = await db.execute(select(DBProject))
    db_projects = len(result.scalars().all())

    result = await db.execute(select(DBTask))
    db_tasks = len(result.scalars().all())

    return {
        **manager_stats,
        "db_projects": db_projects,
        "db_tasks": db_tasks,
    }


@router.get("/models")
async def get_models() -> dict[str, Any]:
    """Get available models and tier assignments.

    Returns information about:
    - Available models from kiro-cli
    - Current tier assignments (advanced, balanced, fast)
    - Credit multipliers for cost estimation
    """
    return get_available_models_info()


@router.post("/models/refresh")
async def refresh_models() -> dict[str, Any]:
    """Refresh available models by re-querying kiro-cli.

    Use this after updating kiro-cli to discover new models.
    """
    models = refresh_available_models()
    return {
        "refreshed": True,
        "available_models": models,
        "current_assignments": get_available_models_info()["tier_assignments"],
    }


@router.get("/models/cost-estimate")
async def estimate_cost(
    task_count: int = 10,
    avg_tokens_per_task: int = 2000,
) -> dict[str, Any]:
    """Estimate cost savings from tiered model selection.

    Args:
        task_count: Expected number of tasks
        avg_tokens_per_task: Average tokens per task

    Returns:
        Cost comparison between all-top-tier and tiered selection
    """
    return model_selector.estimate_cost_savings(
        task_count=task_count,
        avg_tokens_per_task=avg_tokens_per_task,
    )


async def _save_project_state(db: AsyncSession, project: ProjectPlan) -> None:
    """Save project state to database."""
    try:
        result = await db.execute(
            select(DBProject).where(DBProject.id == project.id)
        )
        db_project = result.scalar_one_or_none()

        if db_project:
            db_project.status = project.status.value
            db_project.total_iterations = project.total_iterations
            db_project.branch_name = project.branch_name
            db_project.pr_url = project.pr_url
            db_project.error = project.error
            db_project.started_at = project.started_at
            db_project.completed_at = project.completed_at
            db_project.paused_at = project.paused_at

        # Save tasks
        for task in project.tasks:
            result = await db.execute(
                select(DBTask).where(DBTask.id == task.id)
            )
            db_task = result.scalar_one_or_none()

            if db_task:
                db_task.status = task.status.value
                db_task.iterations = [i.to_dict() for i in task.iterations]
                db_task.final_commit_sha = task.final_commit_sha
                db_task.error = task.error
                db_task.started_at = task.started_at
                db_task.completed_at = task.completed_at
            else:
                db_task = DBTask(
                    id=task.id,
                    project_id=project.id,
                    title=task.title,
                    description=task.description,
                    agent_type=task.agent_type,
                    status=task.status.value,
                    depends_on=task.depends_on,
                    quality_gates=[g.to_dict() for g in task.quality_gates],
                    iterations=[i.to_dict() for i in task.iterations],
                    target_files=task.target_files,
                    max_attempts=task.max_attempts,
                    priority=task.priority,
                    final_commit_sha=task.final_commit_sha,
                    error=task.error,
                    started_at=task.started_at,
                    completed_at=task.completed_at,
                )
                db.add(db_task)

        await db.commit()

    except Exception as e:
        logger.error(f"Failed to save project state: {e}")


def _calculate_progress(project_id: str) -> float:
    """Calculate project progress from in-memory state."""
    project = project_manager.get(project_id)
    if project:
        return project.progress
    return 0.0
