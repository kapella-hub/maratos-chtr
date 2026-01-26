"""Subagent API endpoints."""

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from enum import Enum
from pydantic import BaseModel, Field

from app.subagents.manager import subagent_manager, TaskStatus
from app.subagents.runner import subagent_runner

router = APIRouter(prefix="/subagents")


class ValidAgentId(str, Enum):
    """Valid agent IDs for spawning tasks."""
    MO = "mo"
    ARCHITECT = "architect"
    CODER = "coder"
    REVIEWER = "reviewer"
    TESTER = "tester"
    DOCS = "docs"
    DEVOPS = "devops"


class SpawnTaskRequest(BaseModel):
    """Request to spawn a subagent task."""
    task: str = Field(min_length=1, max_length=50000)
    agent_id: ValidAgentId = ValidAgentId.MO
    context: dict[str, Any] | None = None


class RunSkillRequest(BaseModel):
    """Request to run a skill as subagent."""
    skill_id: str = Field(min_length=1, max_length=100)
    context: dict[str, Any] | None = None


@router.post("/spawn")
async def spawn_task(request: SpawnTaskRequest) -> dict[str, Any]:
    """Spawn a subagent to work on a task in the background."""
    task = await subagent_runner.run_task(
        task_description=request.task,
        agent_id=request.agent_id.value,
        context=request.context,
    )
    return task.to_dict()


@router.post("/skill")
async def run_skill_task(request: RunSkillRequest) -> dict[str, Any]:
    """Run a skill as a subagent task."""
    try:
        task = await subagent_runner.run_skill(
            skill_id=request.skill_id,
            context=request.context,
        )
        return task.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/tasks")
async def list_tasks(
    status: str | None = None,
    agent_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
) -> list[dict[str, Any]]:
    """List subagent tasks."""
    task_status = TaskStatus(status) if status else None
    tasks = subagent_manager.list_tasks(
        status=task_status,
        agent_id=agent_id,
        limit=limit,
    )
    return [t.to_dict() for t in tasks]


@router.get("/tasks/{task_id}")
async def get_task(task_id: str) -> dict[str, Any]:
    """Get a specific task."""
    task = subagent_manager.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")
    return task.to_dict()


@router.post("/tasks/{task_id}/cancel")
async def cancel_task(task_id: str) -> dict[str, str]:
    """Cancel a running task."""
    if await subagent_manager.cancel(task_id):
        return {"status": "cancelled"}
    return {"status": "not_running"}


@router.get("/running")
async def get_running_count() -> dict[str, int]:
    """Get count of running tasks."""
    return {"running": subagent_manager.get_running_count()}


@router.post("/cleanup")
async def cleanup_old_tasks(max_age_hours: int = 24) -> dict[str, int]:
    """Clean up old completed tasks."""
    removed = subagent_manager.cleanup_old(max_age_hours=max_age_hours)
    return {"removed": removed}
