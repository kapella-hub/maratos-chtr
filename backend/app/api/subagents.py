"""Subagent API endpoints."""

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from enum import Enum
from pydantic import BaseModel, Field

from app.subagents.manager import subagent_manager, TaskStatus
from app.subagents.runner import subagent_runner
from app.subagents.metrics import task_metrics

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


@router.get("/rate-limit")
async def get_rate_limit_status() -> dict[str, Any]:
    """Get current rate limit status including queue information."""
    return subagent_manager.get_rate_limit_status()


class RateLimitConfig(BaseModel):
    """Rate limit configuration."""
    max_total_concurrent: int | None = None
    max_per_agent: int | None = None


@router.put("/rate-limit")
async def configure_rate_limits(config: RateLimitConfig) -> dict[str, Any]:
    """Configure rate limits for agent spawning."""
    subagent_manager.configure_rate_limits(
        max_total_concurrent=config.max_total_concurrent,
        max_per_agent=config.max_per_agent,
    )
    return subagent_manager.get_rate_limit_status()


@router.post("/cleanup")
async def cleanup_old_tasks(max_age_hours: int = 24) -> dict[str, int]:
    """Clean up old completed tasks."""
    removed = subagent_manager.cleanup_old(max_age_hours=max_age_hours)
    return {"removed": removed}


# --- Metrics Endpoints ---


@router.get("/metrics")
async def get_all_metrics() -> dict[str, Any]:
    """Get aggregated metrics for all agents."""
    agent_metrics = task_metrics.get_all_agent_metrics()
    return {
        "agents": {k: v.to_dict() for k, v in agent_metrics.items()},
        "recent_tasks": [m.to_dict() for m in task_metrics.get_recent_metrics(10)],
        "failure_patterns": task_metrics.get_failure_patterns(),
    }


@router.get("/metrics/{agent_id}")
async def get_agent_metrics(agent_id: str) -> dict[str, Any]:
    """Get metrics for a specific agent."""
    metrics = task_metrics.get_agent_metrics(agent_id)
    recommendation = task_metrics.get_sizing_recommendation(agent_id)
    return {
        "metrics": metrics.to_dict(),
        "sizing_recommendation": recommendation.to_dict(),
        "failure_patterns": task_metrics.get_failure_patterns(agent_id),
    }


@router.get("/metrics/{agent_id}/sizing")
async def get_sizing_recommendation(agent_id: str) -> dict[str, Any]:
    """Get task sizing recommendation for an agent."""
    return task_metrics.get_sizing_recommendation(agent_id).to_dict()


# --- Failure & Recovery Endpoints ---


@router.get("/failures")
async def get_failure_stats() -> dict[str, Any]:
    """Get failure statistics and recent failures."""
    stats = subagent_manager.get_failure_stats()
    recent = subagent_manager.get_recent_failures(limit=20)
    return {
        "stats": stats,
        "recent_failures": recent,
    }


@router.get("/failures/{agent_id}")
async def get_agent_failures(
    agent_id: str,
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    """Get recent failures for a specific agent."""
    failures = subagent_manager.get_recent_failures(agent_id=agent_id, limit=limit)
    return {
        "agent_id": agent_id,
        "count": len(failures),
        "failures": failures,
    }


class RetryTaskRequest(BaseModel):
    """Request to retry a failed task."""
    pass  # No additional fields needed, task_id is in URL


@router.post("/tasks/{task_id}/retry")
async def retry_task(task_id: str) -> dict[str, Any]:
    """Retry a failed task.

    This will reset the task and attempt to run it again with the same parameters.
    """
    task = subagent_manager.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")

    if task.status.value not in ("failed", "timed_out"):
        raise HTTPException(
            status_code=400,
            detail=f"Task is not in a retryable state: {task.status.value}"
        )

    # Need to recreate the work function - spawn a new task with same description
    new_task = await subagent_runner.run_task(
        task_description=task.description,
        agent_id=task.agent_id,
        context={"retry_of": task_id},
    )

    return {
        "status": "retrying",
        "original_task_id": task_id,
        "new_task": new_task.to_dict(),
    }


class FallbackRequest(BaseModel):
    """Request to spawn a fallback task."""
    fallback_agent_id: ValidAgentId = ValidAgentId.REVIEWER


@router.post("/tasks/{task_id}/fallback")
async def spawn_fallback(task_id: str, request: FallbackRequest) -> dict[str, Any]:
    """Spawn a fallback task to diagnose/fix a failed task.

    This spawns a new task using a different agent to analyze the failure
    and potentially provide a solution.
    """
    task = subagent_manager.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")

    if task.status.value not in ("failed", "timed_out"):
        raise HTTPException(
            status_code=400,
            detail=f"Task must be failed to spawn fallback: {task.status.value}"
        )

    fallback_task = await subagent_runner.run_fallback_task(
        failed_task=task,
        fallback_agent_id=request.fallback_agent_id.value,
    )

    return {
        "status": "fallback_spawned",
        "original_task_id": task_id,
        "fallback_task": fallback_task.to_dict(),
    }


@router.post("/tasks/{task_id}/diagnose")
async def diagnose_failure(task_id: str) -> dict[str, Any]:
    """Spawn a diagnostic task to analyze why a task failed.

    Uses the reviewer agent to analyze the failure and provide recommendations.
    """
    task = subagent_manager.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")

    if task.status.value not in ("failed", "timed_out"):
        raise HTTPException(
            status_code=400,
            detail=f"Task must be failed to diagnose: {task.status.value}"
        )

    diagnostic_task = await subagent_runner.diagnose_failure(failed_task=task)

    return {
        "status": "diagnosis_started",
        "original_task_id": task_id,
        "diagnostic_task": diagnostic_task.to_dict(),
    }


@router.get("/tasks/{task_id}/fallback")
async def get_fallback_task(task_id: str) -> dict[str, Any]:
    """Get the fallback task for an original task, if any."""
    task = subagent_manager.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")

    fallback = subagent_manager.get_fallback_task(task_id)
    if not fallback:
        return {"original_task_id": task_id, "has_fallback": False}

    return {
        "original_task_id": task_id,
        "has_fallback": True,
        "fallback_task": fallback.to_dict(),
    }
