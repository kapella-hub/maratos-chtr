"""Repositories for orchestration persistence.

Provides database-backed storage for orchestration runs, tasks, and artifacts,
enabling durability across server restarts.
"""

import hashlib
import logging
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

import app.database as db_module
from app.database import (
    OrchestrationRun,
    OrchestrationTask,
    TaskArtifact,
    TaskLog,
)


def get_session():
    """Get the current session factory (supports test patching)."""
    return db_module.async_session_factory

logger = logging.getLogger(__name__)


# =============================================================================
# Run Repository
# =============================================================================


class RunRepository:
    """Repository for orchestration run persistence.

    Handles CRUD operations for OrchestrationRun records.
    """

    @staticmethod
    async def create(
        run_id: str,
        original_prompt: str,
        workspace_path: str | None = None,
        session_id: str | None = None,
        mode: str = "inline",
        config: dict | None = None,
    ) -> OrchestrationRun:
        """Create a new orchestration run record."""
        async with get_session()() as db:
            run = OrchestrationRun(
                id=run_id,
                original_prompt=original_prompt,
                workspace_path=workspace_path,
                session_id=session_id,
                mode=mode,
                state="intake",
                config_json=config,
                started_at=datetime.utcnow(),
            )
            db.add(run)
            await db.commit()
            await db.refresh(run)
            logger.info(f"Created orchestration run {run_id}")
            return run

    @staticmethod
    async def get(run_id: str) -> OrchestrationRun | None:
        """Get a run by ID."""
        async with get_session()() as db:
            result = await db.execute(
                select(OrchestrationRun).where(OrchestrationRun.id == run_id)
            )
            return result.scalar_one_or_none()

    @staticmethod
    async def get_by_session(session_id: str) -> OrchestrationRun | None:
        """Get the active run for a session (if any)."""
        async with get_session()() as db:
            result = await db.execute(
                select(OrchestrationRun)
                .where(OrchestrationRun.session_id == session_id)
                .where(
                    OrchestrationRun.state.notin_(
                        ["done", "failed", "cancelled"]
                    )
                )
                .order_by(OrchestrationRun.created_at.desc())
                .limit(1)
            )
            return result.scalar_one_or_none()

    @staticmethod
    async def list_active() -> list[OrchestrationRun]:
        """List all active (non-terminal) runs."""
        async with get_session()() as db:
            result = await db.execute(
                select(OrchestrationRun)
                .where(
                    OrchestrationRun.state.notin_(
                        ["done", "failed", "cancelled"]
                    )
                )
                .order_by(OrchestrationRun.created_at.desc())
            )
            return list(result.scalars().all())

    @staticmethod
    async def list_by_status(status: str, limit: int = 100) -> list[OrchestrationRun]:
        """List runs by status."""
        async with get_session()() as db:
            result = await db.execute(
                select(OrchestrationRun)
                .where(OrchestrationRun.state == status)
                .order_by(OrchestrationRun.created_at.desc())
                .limit(limit)
            )
            return list(result.scalars().all())

    @staticmethod
    async def update_state(
        run_id: str,
        state: str,
        error: str | None = None,
        error_details: dict | None = None,
    ) -> bool:
        """Update run state."""
        async with get_session()() as db:
            result = await db.execute(
                select(OrchestrationRun).where(OrchestrationRun.id == run_id)
            )
            run = result.scalar_one_or_none()
            if not run:
                return False

            run.state = state
            if error:
                run.error = error
            if error_details:
                run.error_details = error_details

            # Set timestamps based on state
            if state == "done" or state == "failed" or state == "cancelled":
                run.completed_at = datetime.utcnow()
            elif state == "paused":
                run.paused_at = datetime.utcnow()

            await db.commit()
            logger.debug(f"Run {run_id} state updated to {state}")
            return True

    @staticmethod
    async def update_plan(run_id: str, plan_json: dict) -> bool:
        """Update the plan for a run."""
        async with get_session()() as db:
            result = await db.execute(
                select(OrchestrationRun).where(OrchestrationRun.id == run_id)
            )
            run = result.scalar_one_or_none()
            if not run:
                return False

            run.plan_json = plan_json
            await db.commit()
            logger.debug(f"Run {run_id} plan updated")
            return True

    @staticmethod
    async def update_graph_state(run_id: str, graph_state: dict) -> bool:
        """Update the graph state for resume support."""
        async with get_session()() as db:
            result = await db.execute(
                select(OrchestrationRun).where(OrchestrationRun.id == run_id)
            )
            run = result.scalar_one_or_none()
            if not run:
                return False

            run.graph_state = graph_state
            await db.commit()
            return True

    @staticmethod
    async def set_resume_state(run_id: str, resume_state: str | None) -> bool:
        """Set the resume state for a paused run."""
        async with get_session()() as db:
            result = await db.execute(
                select(OrchestrationRun).where(OrchestrationRun.id == run_id)
            )
            run = result.scalar_one_or_none()
            if not run:
                return False

            run.resume_state = resume_state
            if resume_state is None:
                run.paused_at = None
            await db.commit()
            return True

    @staticmethod
    async def get_full_state(run_id: str) -> dict | None:
        """Get full run state for resume."""
        async with get_session()() as db:
            result = await db.execute(
                select(OrchestrationRun).where(OrchestrationRun.id == run_id)
            )
            run = result.scalar_one_or_none()
            if not run:
                return None

            return {
                "run_id": run.id,
                "state": run.state,
                "original_prompt": run.original_prompt,
                "workspace_path": run.workspace_path,
                "session_id": run.session_id,
                "started_at": run.started_at.isoformat() if run.started_at else None,
                "completed_at": run.completed_at.isoformat() if run.completed_at else None,
                "error": run.error,
                "error_details": run.error_details,
                "paused_at": run.paused_at.isoformat() if run.paused_at else None,
                "resume_state": run.resume_state,
                "plan": run.plan_json,
                "graph_state": run.graph_state,
                "config": run.config_json,
            }

    @staticmethod
    async def delete(run_id: str) -> bool:
        """Delete a run and all associated data."""
        async with get_session()() as db:
            # Delete in order: logs, artifacts, tasks, run
            await db.execute(
                TaskLog.__table__.delete().where(TaskLog.run_id == run_id)
            )
            await db.execute(
                TaskArtifact.__table__.delete().where(TaskArtifact.run_id == run_id)
            )
            await db.execute(
                OrchestrationTask.__table__.delete().where(
                    OrchestrationTask.run_id == run_id
                )
            )
            await db.execute(
                OrchestrationRun.__table__.delete().where(
                    OrchestrationRun.id == run_id
                )
            )
            await db.commit()
            logger.info(f"Deleted run {run_id} and all associated data")
            return True


# =============================================================================
# Task Repository
# =============================================================================


class TaskRepository:
    """Repository for orchestration task persistence."""

    @staticmethod
    async def create(
        task_id: str,
        run_id: str,
        title: str,
        description: str,
        agent_id: str,
        depends_on: list[str] | None = None,
        target_files: list[str] | None = None,
        acceptance_criteria: list[dict] | None = None,
        skill_id: str | None = None,
        max_attempts: int = 3,
        priority: int = 0,
    ) -> OrchestrationTask:
        """Create a new task record."""
        async with get_session()() as db:
            task = OrchestrationTask(
                id=task_id,
                run_id=run_id,
                title=title,
                description=description,
                agent_id=agent_id,
                depends_on=depends_on or [],
                target_files=target_files or [],
                acceptance_criteria=acceptance_criteria or [],
                skill_id=skill_id,
                max_attempts=max_attempts,
                priority=priority,
                status="pending",
            )
            db.add(task)
            await db.commit()
            await db.refresh(task)
            logger.debug(f"Created task {task_id} for run {run_id}")
            return task

    @staticmethod
    async def create_many(tasks: list[dict]) -> list[OrchestrationTask]:
        """Bulk create tasks."""
        async with get_session()() as db:
            records = []
            for task_data in tasks:
                task = OrchestrationTask(
                    id=task_data["id"],
                    run_id=task_data["run_id"],
                    title=task_data["title"],
                    description=task_data["description"],
                    agent_id=task_data["agent_id"],
                    depends_on=task_data.get("depends_on", []),
                    target_files=task_data.get("target_files", []),
                    acceptance_criteria=task_data.get("acceptance_criteria", []),
                    skill_id=task_data.get("skill_id"),
                    max_attempts=task_data.get("max_attempts", 3),
                    priority=task_data.get("priority", 0),
                    status="pending",
                )
                db.add(task)
                records.append(task)
            await db.commit()
            logger.debug(f"Bulk created {len(records)} tasks")
            return records

    @staticmethod
    async def get(task_id: str) -> OrchestrationTask | None:
        """Get a task by ID."""
        async with get_session()() as db:
            result = await db.execute(
                select(OrchestrationTask).where(OrchestrationTask.id == task_id)
            )
            return result.scalar_one_or_none()

    @staticmethod
    async def get_by_run(run_id: str) -> list[OrchestrationTask]:
        """Get all tasks for a run."""
        async with get_session()() as db:
            result = await db.execute(
                select(OrchestrationTask)
                .where(OrchestrationTask.run_id == run_id)
                .order_by(OrchestrationTask.priority.desc(), OrchestrationTask.created_at)
            )
            return list(result.scalars().all())

    @staticmethod
    async def get_by_status(run_id: str, status: str) -> list[OrchestrationTask]:
        """Get tasks by status for a run."""
        async with get_session()() as db:
            result = await db.execute(
                select(OrchestrationTask)
                .where(OrchestrationTask.run_id == run_id)
                .where(OrchestrationTask.status == status)
                .order_by(OrchestrationTask.priority.desc())
            )
            return list(result.scalars().all())

    @staticmethod
    async def update_status(
        task_id: str,
        status: str,
        error: str | None = None,
    ) -> bool:
        """Update task status."""
        async with get_session()() as db:
            result = await db.execute(
                select(OrchestrationTask).where(OrchestrationTask.id == task_id)
            )
            task = result.scalar_one_or_none()
            if not task:
                return False

            task.status = status
            if error:
                task.error = error

            # Set timestamps
            if status == "running" and task.started_at is None:
                task.started_at = datetime.utcnow()
            elif status in ("completed", "failed", "skipped"):
                task.completed_at = datetime.utcnow()

            await db.commit()
            return True

    @staticmethod
    async def update_result(
        task_id: str,
        result: str,
        verification_results: dict | None = None,
    ) -> bool:
        """Update task result."""
        async with get_session()() as db:
            db_result = await db.execute(
                select(OrchestrationTask).where(OrchestrationTask.id == task_id)
            )
            task = db_result.scalar_one_or_none()
            if not task:
                return False

            task.result = result
            if verification_results:
                task.verification_results = verification_results
            await db.commit()
            return True

    @staticmethod
    async def increment_attempt(task_id: str) -> int:
        """Increment task attempt counter and return new value."""
        async with get_session()() as db:
            result = await db.execute(
                select(OrchestrationTask).where(OrchestrationTask.id == task_id)
            )
            task = result.scalar_one_or_none()
            if not task:
                return 0

            task.attempt += 1
            task.status = "pending"  # Reset to pending for retry
            task.started_at = None
            task.completed_at = None
            await db.commit()
            return task.attempt

    @staticmethod
    async def get_task_summary(run_id: str) -> dict[str, int]:
        """Get task status summary for a run."""
        async with get_session()() as db:
            result = await db.execute(
                select(OrchestrationTask).where(OrchestrationTask.run_id == run_id)
            )
            tasks = result.scalars().all()

            summary = {
                "total": 0,
                "pending": 0,
                "running": 0,
                "completed": 0,
                "failed": 0,
                "blocked": 0,
                "skipped": 0,
            }
            for task in tasks:
                summary["total"] += 1
                status = task.status
                if status in summary:
                    summary[status] += 1
            return summary


# =============================================================================
# Artifact Repository
# =============================================================================


class ArtifactRepository:
    """Repository for task artifact persistence."""

    @staticmethod
    async def create(
        task_id: str,
        run_id: str,
        name: str,
        artifact_type: str,
        path: str | None = None,
        content: str | None = None,
        extra_data: dict | None = None,
        producer_agent: str | None = None,
    ) -> TaskArtifact:
        """Create a new artifact record."""
        artifact_id = str(uuid.uuid4())

        # Calculate content hash if content provided
        content_hash = None
        if content:
            content_hash = hashlib.sha256(content.encode()).hexdigest()

        async with get_session()() as db:
            artifact = TaskArtifact(
                id=artifact_id,
                task_id=task_id,
                run_id=run_id,
                name=name,
                artifact_type=artifact_type,
                path=path,
                content=content,
                content_hash=content_hash,
                extra_data=extra_data,
                producer_agent=producer_agent,
            )
            db.add(artifact)
            await db.commit()
            await db.refresh(artifact)
            logger.debug(f"Created artifact {name} for task {task_id}")
            return artifact

    @staticmethod
    async def get(artifact_id: str) -> TaskArtifact | None:
        """Get an artifact by ID."""
        async with get_session()() as db:
            result = await db.execute(
                select(TaskArtifact).where(TaskArtifact.id == artifact_id)
            )
            return result.scalar_one_or_none()

    @staticmethod
    async def get_by_task(task_id: str) -> list[TaskArtifact]:
        """Get all artifacts for a task."""
        async with get_session()() as db:
            result = await db.execute(
                select(TaskArtifact)
                .where(TaskArtifact.task_id == task_id)
                .order_by(TaskArtifact.created_at)
            )
            return list(result.scalars().all())

    @staticmethod
    async def get_by_run(run_id: str) -> list[TaskArtifact]:
        """Get all artifacts for a run."""
        async with get_session()() as db:
            result = await db.execute(
                select(TaskArtifact)
                .where(TaskArtifact.run_id == run_id)
                .order_by(TaskArtifact.created_at)
            )
            return list(result.scalars().all())

    @staticmethod
    async def get_by_type(run_id: str, artifact_type: str) -> list[TaskArtifact]:
        """Get artifacts by type for a run."""
        async with get_session()() as db:
            result = await db.execute(
                select(TaskArtifact)
                .where(TaskArtifact.run_id == run_id)
                .where(TaskArtifact.artifact_type == artifact_type)
                .order_by(TaskArtifact.created_at)
            )
            return list(result.scalars().all())

    @staticmethod
    async def delete_by_task(task_id: str) -> int:
        """Delete all artifacts for a task."""
        async with get_session()() as db:
            result = await db.execute(
                TaskArtifact.__table__.delete().where(TaskArtifact.task_id == task_id)
            )
            await db.commit()
            return result.rowcount


# =============================================================================
# Log Repository
# =============================================================================


class LogRepository:
    """Repository for task log persistence."""

    @staticmethod
    async def create(
        task_id: str,
        run_id: str,
        message: str,
        level: str = "info",
        tool_name: str | None = None,
        tool_input: dict | None = None,
        tool_output: str | None = None,
        tool_duration_ms: float | None = None,
    ) -> TaskLog:
        """Create a new log entry."""
        log_id = str(uuid.uuid4())

        async with get_session()() as db:
            log = TaskLog(
                id=log_id,
                task_id=task_id,
                run_id=run_id,
                level=level,
                message=message,
                tool_name=tool_name,
                tool_input=tool_input,
                tool_output=tool_output,
                tool_duration_ms=tool_duration_ms,
            )
            db.add(log)
            await db.commit()
            return log

    @staticmethod
    async def create_many(logs: list[dict]) -> int:
        """Bulk create log entries."""
        async with get_session()() as db:
            for log_data in logs:
                log = TaskLog(
                    id=str(uuid.uuid4()),
                    task_id=log_data["task_id"],
                    run_id=log_data["run_id"],
                    level=log_data.get("level", "info"),
                    message=log_data["message"],
                    tool_name=log_data.get("tool_name"),
                    tool_input=log_data.get("tool_input"),
                    tool_output=log_data.get("tool_output"),
                    tool_duration_ms=log_data.get("tool_duration_ms"),
                )
                db.add(log)
            await db.commit()
            return len(logs)

    @staticmethod
    async def get_by_task(
        task_id: str,
        level: str | None = None,
        limit: int = 1000,
    ) -> list[TaskLog]:
        """Get logs for a task."""
        async with get_session()() as db:
            query = select(TaskLog).where(TaskLog.task_id == task_id)
            if level:
                query = query.where(TaskLog.level == level)
            query = query.order_by(TaskLog.created_at).limit(limit)
            result = await db.execute(query)
            return list(result.scalars().all())

    @staticmethod
    async def get_by_run(
        run_id: str,
        level: str | None = None,
        limit: int = 5000,
    ) -> list[TaskLog]:
        """Get all logs for a run."""
        async with get_session()() as db:
            query = select(TaskLog).where(TaskLog.run_id == run_id)
            if level:
                query = query.where(TaskLog.level == level)
            query = query.order_by(TaskLog.created_at).limit(limit)
            result = await db.execute(query)
            return list(result.scalars().all())

    @staticmethod
    async def get_tool_audit_trail(
        run_id: str,
        tool_name: str | None = None,
    ) -> list[TaskLog]:
        """Get tool invocation audit trail for a run."""
        async with get_session()() as db:
            query = (
                select(TaskLog)
                .where(TaskLog.run_id == run_id)
                .where(TaskLog.tool_name.isnot(None))
            )
            if tool_name:
                query = query.where(TaskLog.tool_name == tool_name)
            query = query.order_by(TaskLog.created_at)
            result = await db.execute(query)
            return list(result.scalars().all())

    @staticmethod
    async def delete_by_run(run_id: str) -> int:
        """Delete all logs for a run."""
        async with get_session()() as db:
            result = await db.execute(
                TaskLog.__table__.delete().where(TaskLog.run_id == run_id)
            )
            await db.commit()
            return result.rowcount
