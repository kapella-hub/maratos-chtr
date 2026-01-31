"""Persistent Orchestration Engine.

Wraps the OrchestrationEngine with database persistence for durability
across server restarts.
"""

import logging
import json
from datetime import datetime
from typing import Any, AsyncIterator

from app.autonomous.engine import (
    EngineEvent,
    EngineEventType,
    OrchestrationEngine,
    RunConfig,
    RunContext,
    RunState,
)
from app.autonomous.planner_schema import ExecutionPlan
from app.autonomous.repositories import (
    ArtifactRepository,
    LogRepository,
    RunRepository,
    TaskRepository,
)
from app.autonomous.task_graph import TaskGraph

logger = logging.getLogger(__name__)


class PersistentOrchestrationEngine:
    """Orchestration engine with database persistence.

    Wraps the base OrchestrationEngine and adds persistence hooks for:
    - Run metadata and state
    - Plan JSON
    - Task graph state
    - Task logs and tool audit trail
    - Artifacts
    """

    def __init__(
        self,
        engine: OrchestrationEngine | None = None,
    ):
        """Initialize the persistent engine.

        Args:
            engine: Base engine to wrap (creates default if None)
        """
        from app.autonomous.engine import get_engine
        self.engine = engine or get_engine()

    async def run(
        self,
        prompt: str,
        workspace_path: str | None = None,
        session_id: str | None = None,
        config: RunConfig | None = None,
        existing_plan: ExecutionPlan | None = None,
        mode: str = "inline",
    ) -> AsyncIterator[EngineEvent]:
        """Execute an orchestration run with persistence.

        Args:
            prompt: The original user request
            workspace_path: Optional workspace directory
            session_id: Optional session ID for inline mode
            config: Run configuration
            existing_plan: Skip planning and use this plan directly
            mode: Run mode ("inline" or "autonomous")

        Yields:
            EngineEvent objects for SSE streaming
        """
        run_id = None
        ctx = None

        # Check if resuming from persisted state
        if config and config.resume_from_state:
            run_id = config.resume_from_state.get("run_id")
            logger.info(f"Resuming persisted run {run_id}")
        else:
            # Create a new run record
            import uuid
            run_id = f"run-{uuid.uuid4().hex[:12]}"

            config_dict = None
            if config:
                config_dict = {
                    "parallel_tasks": config.parallel_tasks,
                    "task_timeout_seconds": config.task_timeout_seconds,
                    "max_task_retries": config.max_task_retries,
                    "run_verification": config.run_verification,
                    "fail_fast": config.fail_fast,
                    "planner_model": config.planner_model,
                    "planning_timeout_seconds": config.planning_timeout_seconds,
                }

            await RunRepository.create(
                run_id=run_id,
                original_prompt=prompt,
                workspace_path=workspace_path,
                session_id=session_id,
                mode=mode,
                config=config_dict,
            )

        try:
            async for event in self.engine.run(
                prompt=prompt,
                workspace_path=workspace_path,
                session_id=session_id,
                config=config,
                existing_plan=existing_plan,
            ):
                # Persist based on event type
                await self._handle_event(event, run_id)
                yield event

        except Exception as e:
            # Mark run as failed
            await RunRepository.update_state(
                run_id=run_id,
                state="failed",
                error=str(e),
            )
            raise

    async def _handle_event(self, event: EngineEvent, run_id: str) -> None:
        """Handle persistence for an event."""
        etype = event.type

        # Run state changes
        if etype == EngineEventType.RUN_STATE:
            state = event.data.get("state")
            error = event.data.get("error")
            await RunRepository.update_state(
                run_id=run_id,
                state=state,
                error=error,
            )

        # Planning completed - persist plan
        elif etype == EngineEventType.PLANNING_COMPLETED:
            plan = event.data.get("plan")
            if plan:
                # Convert Pydantic model to JSON-safe dict (handling datetimes)
                # Use robust default=str to handle any non-serializable objects (like datetime)
                try:
                    if hasattr(plan, "model_dump"):
                        data = plan.model_dump()
                    elif hasattr(plan, "dict"):
                        data = plan.dict()
                    else:
                        data = plan
                        
                    plan_json = json.loads(json.dumps(data, default=str))
                except Exception as e:
                    logger.error(f"Failed to serialize plan: {e}")
                    plan_json = {} # Safe fallback

                await RunRepository.update_plan(run_id, plan_json)

        # Task graph built - persist tasks
        elif etype == EngineEventType.TASK_GRAPH_BUILT:
            # Get the current context to access tasks
            ctx_state = self.engine.get_run_state(run_id)
            if ctx_state and ctx_state.get("plan"):
                plan = ctx_state["plan"]
                tasks_data = []
                for task in plan.get("tasks", []):
                    tasks_data.append({
                        "id": task["id"],
                        "run_id": run_id,
                        "title": task["title"],
                        "description": task["description"],
                        "agent_id": task["agent_id"],
                        "depends_on": task.get("depends_on", []),
                        "target_files": task.get("target_files", []),
                        "acceptance_criteria": task.get("acceptance", []),
                        "skill_id": task.get("skill_id"),
                        "max_attempts": task.get("max_attempts", 3),
                        "priority": task.get("priority", 0),
                    })
                if tasks_data:
                    await TaskRepository.create_many(tasks_data)

        # Task started
        elif etype == EngineEventType.TASK_STARTED:
            task_id = event.data.get("task_id")
            if task_id:
                await TaskRepository.update_status(task_id, "running")
                await LogRepository.create(
                    task_id=task_id,
                    run_id=run_id,
                    message=f"Task started: {event.data.get('title', 'Unknown')}",
                    level="info",
                )

        # Task completed
        elif etype == EngineEventType.TASK_COMPLETED:
            task_id = event.data.get("task_id")
            if task_id:
                result = event.data.get("result", {})
                await TaskRepository.update_status(task_id, "completed")
                await TaskRepository.update_result(
                    task_id,
                    result=str(result.get("response", "")),
                    verification_results=event.data.get("verification_results"),
                )
                await LogRepository.create(
                    task_id=task_id,
                    run_id=run_id,
                    message="Task completed successfully",
                    level="info",
                )

                # Persist artifacts
                artifacts = event.data.get("artifacts", {})
                for name, value in artifacts.items():
                    await ArtifactRepository.create(
                        task_id=task_id,
                        run_id=run_id,
                        name=name,
                        artifact_type=type(value).__name__,
                        content=str(value) if not isinstance(value, (dict, list)) else None,
                        extra_data=value if isinstance(value, (dict, list)) else None,
                        producer_agent=event.data.get("agent_id"),
                    )

        # Task failed
        elif etype == EngineEventType.TASK_FAILED:
            task_id = event.data.get("task_id")
            error = event.data.get("error")
            if task_id:
                await TaskRepository.update_status(task_id, "failed", error=error)
                await LogRepository.create(
                    task_id=task_id,
                    run_id=run_id,
                    message=f"Task failed: {error}",
                    level="error",
                )

        # Task retrying
        elif etype == EngineEventType.TASK_RETRYING:
            task_id = event.data.get("task_id")
            if task_id:
                await TaskRepository.increment_attempt(task_id)
                await LogRepository.create(
                    task_id=task_id,
                    run_id=run_id,
                    message=f"Task retrying: {event.data.get('reason')}",
                    level="warning",
                )

        # Artifact created
        elif etype == EngineEventType.ARTIFACT_CREATED:
            task_id = event.data.get("task_id")
            if task_id:
                await ArtifactRepository.create(
                    task_id=task_id,
                    run_id=run_id,
                    name=event.data.get("artifact_name", "unknown"),
                    artifact_type=event.data.get("artifact_type", "unknown"),
                    path=event.data.get("path"),
                    producer_agent=event.data.get("agent_id"),
                )

        # Verification result
        elif etype == EngineEventType.VERIFICATION_RESULT:
            task_id = event.data.get("task_id")
            if task_id:
                await LogRepository.create(
                    task_id=task_id,
                    run_id=run_id,
                    message=f"Verification {event.data.get('criterion_id')}: {'passed' if event.data.get('passed') else 'failed'}",
                    level="info" if event.data.get("passed") else "warning",
                )

        # Run error
        elif etype == EngineEventType.RUN_ERROR:
            error = event.data.get("error")
            await RunRepository.update_state(
                run_id=run_id,
                state="failed",
                error=error,
            )

        # Paused
        elif etype == EngineEventType.PAUSED:
            # Save graph state for resume
            ctx_state = self.engine.get_run_state(run_id)
            if ctx_state and ctx_state.get("graph_state"):
                await RunRepository.update_graph_state(run_id, ctx_state["graph_state"])

    async def pause(self, run_id: str) -> bool:
        """Pause a running orchestration with persistence."""
        success = await self.engine.pause(run_id)
        if success:
            ctx_state = self.engine.get_run_state(run_id)
            if ctx_state:
                await RunRepository.update_state(run_id, "paused")
                await RunRepository.set_resume_state(
                    run_id, ctx_state.get("resume_state")
                )
                if ctx_state.get("graph_state"):
                    await RunRepository.update_graph_state(
                        run_id, ctx_state["graph_state"]
                    )
        return success

    async def resume(self, run_id: str) -> AsyncIterator[EngineEvent]:
        """Resume a paused orchestration from database.

        Loads state from DB and resumes execution.
        """
        # Load state from DB
        db_state = await RunRepository.get_full_state(run_id)
        if not db_state:
            logger.warning(f"No persisted state found for run {run_id}")
            return

        if db_state.get("state") != "paused":
            logger.warning(f"Run {run_id} is not paused (state: {db_state.get('state')})")
            return

        # Create config with resume state
        config = RunConfig(resume_from_state=db_state)

        async for event in self.engine.resume(run_id):
            await self._handle_event(event, run_id)
            yield event

    async def cancel(self, run_id: str) -> bool:
        """Cancel an orchestration run."""
        success = await self.engine.cancel(run_id)
        if success:
            await RunRepository.update_state(run_id, "cancelled")
        return success

    async def get_run_status(self, run_id: str) -> dict | None:
        """Get run status from database."""
        return await RunRepository.get_full_state(run_id)

    async def get_task_status(self, run_id: str) -> dict:
        """Get task summary for a run."""
        return await TaskRepository.get_task_summary(run_id)

    async def get_task_logs(
        self,
        task_id: str,
        level: str | None = None,
    ) -> list[dict]:
        """Get logs for a task."""
        logs = await LogRepository.get_by_task(task_id, level=level)
        return [
            {
                "id": log.id,
                "level": log.level,
                "message": log.message,
                "tool_name": log.tool_name,
                "tool_input": log.tool_input,
                "tool_output": log.tool_output,
                "tool_duration_ms": log.tool_duration_ms,
                "created_at": log.created_at.isoformat(),
            }
            for log in logs
        ]

    async def get_run_logs(
        self,
        run_id: str,
        level: str | None = None,
    ) -> list[dict]:
        """Get all logs for a run."""
        logs = await LogRepository.get_by_run(run_id, level=level)
        return [
            {
                "id": log.id,
                "task_id": log.task_id,
                "level": log.level,
                "message": log.message,
                "tool_name": log.tool_name,
                "created_at": log.created_at.isoformat(),
            }
            for log in logs
        ]

    async def get_artifacts(self, run_id: str) -> list[dict]:
        """Get all artifacts for a run."""
        artifacts = await ArtifactRepository.get_by_run(run_id)
        return [
            {
                "id": artifact.id,
                "task_id": artifact.task_id,
                "name": artifact.name,
                "artifact_type": artifact.artifact_type,
                "path": artifact.path,
                "content_hash": artifact.content_hash,
                "producer_agent": artifact.producer_agent,
                "created_at": artifact.created_at.isoformat(),
            }
            for artifact in artifacts
        ]

    async def load_interrupted_runs(self) -> list[dict]:
        """Load runs that were interrupted (running/paused when server stopped)."""
        runs = await RunRepository.list_active()
        return [
            {
                "run_id": run.id,
                "state": run.state,
                "session_id": run.session_id,
                "mode": run.mode,
                "created_at": run.created_at.isoformat(),
            }
            for run in runs
        ]

    async def get_run_by_session(self, session_id: str) -> dict | None:
        """Get the active run for a session."""
        run = await RunRepository.get_by_session(session_id)
        if run:
            return {
                "run_id": run.id,
                "state": run.state,
                "mode": run.mode,
                "created_at": run.created_at.isoformat(),
            }
        return None


# =============================================================================
# Query Functions
# =============================================================================


async def get_run_by_session(session_id: str) -> dict | None:
    """Get the active run for a session."""
    run = await RunRepository.get_by_session(session_id)
    if run:
        return {
            "run_id": run.id,
            "state": run.state,
            "mode": run.mode,
            "created_at": run.created_at.isoformat(),
        }
    return None


async def get_run_tasks(run_id: str) -> list[dict]:
    """Get all tasks for a run."""
    tasks = await TaskRepository.get_by_run(run_id)
    return [
        {
            "id": task.id,
            "title": task.title,
            "description": task.description,
            "agent_id": task.agent_id,
            "status": task.status,
            "attempt": task.attempt,
            "depends_on": task.depends_on,
            "error": task.error,
            "started_at": task.started_at.isoformat() if task.started_at else None,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        }
        for task in tasks
    ]


async def get_tool_audit_trail(run_id: str) -> list[dict]:
    """Get tool invocation audit trail for a run."""
    logs = await LogRepository.get_tool_audit_trail(run_id)
    return [
        {
            "task_id": log.task_id,
            "tool_name": log.tool_name,
            "tool_input": log.tool_input,
            "tool_output": log.tool_output,
            "tool_duration_ms": log.tool_duration_ms,
            "created_at": log.created_at.isoformat(),
        }
        for log in logs
    ]


# =============================================================================
# Singleton Instance
# =============================================================================

_persistent_engine: PersistentOrchestrationEngine | None = None


def get_persistent_engine() -> PersistentOrchestrationEngine:
    """Get the global persistent orchestration engine instance."""
    global _persistent_engine
    if _persistent_engine is None:
        _persistent_engine = PersistentOrchestrationEngine()
    return _persistent_engine
