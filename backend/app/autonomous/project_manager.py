"""Project manager for tracking autonomous projects.

Now DB-backed using repositories for durability across restarts.
"""

import asyncio
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from app.autonomous.models import (
    ProjectPlan,
    ProjectStatus,
    ProjectConfig,
)
from app.autonomous.repositories import (
    RunRepository,
    TaskRepository,
    LogRepository,
    ArtifactRepository,
)

logger = logging.getLogger(__name__)


def _run_state_to_project_status(state: str) -> ProjectStatus:
    """Map run state to project status."""
    mapping = {
        "intake": ProjectStatus.PLANNING,
        "plan": ProjectStatus.PLANNING,
        "task_graph": ProjectStatus.PLANNING,
        "execute": ProjectStatus.IN_PROGRESS,
        "verify": ProjectStatus.IN_PROGRESS,
        "synthesize": ProjectStatus.IN_PROGRESS,
        "done": ProjectStatus.COMPLETED,
        "failed": ProjectStatus.FAILED,
        "paused": ProjectStatus.PAUSED,
        "cancelled": ProjectStatus.CANCELLED,
    }
    return mapping.get(state, ProjectStatus.PLANNING)


class ProjectManager:
    """Manages autonomous projects with DB-backed persistence.

    Bridges the legacy ProjectPlan model with the new orchestration engine
    persistence, allowing queries across both in-flight and historical runs.
    """

    def __init__(self) -> None:
        # In-memory cache for active orchestrators (can't persist connections)
        self._running_orchestrators: dict[str, Any] = {}
        self._lock = asyncio.Lock()

    async def create_project(
        self,
        name: str,
        prompt: str,
        workspace_path: str | Path,
        config: ProjectConfig | None = None,
    ) -> ProjectPlan:
        """Create a new autonomous project.

        Creates the project in DB via RunRepository.
        """
        project_id = str(uuid.uuid4())[:8]
        run_id = f"run-{project_id}"

        # Persist to database
        config_dict = None
        if config:
            config_dict = config.model_dump() if hasattr(config, 'model_dump') else config.__dict__

        await RunRepository.create(
            run_id=run_id,
            original_prompt=prompt,
            workspace_path=str(workspace_path),
            session_id=None,  # Autonomous projects don't have session
            mode="autonomous",
            config=config_dict,
        )

        # Return legacy ProjectPlan for backwards compatibility
        project = ProjectPlan(
            id=project_id,
            name=name,
            original_prompt=prompt,
            workspace_path=str(workspace_path),
            status=ProjectStatus.PLANNING,
            config=config or ProjectConfig(),
        )

        logger.info(f"Created project: {project_id} - {name}")
        return project

    async def get(self, project_id: str) -> ProjectPlan | None:
        """Get a project by ID from database."""
        run_id = f"run-{project_id}"
        run = await RunRepository.get(run_id)

        if not run:
            return None

        return self._run_to_project_plan(run, project_id)

    async def get_by_run_id(self, run_id: str) -> ProjectPlan | None:
        """Get a project by its run ID."""
        run = await RunRepository.get(run_id)

        if not run:
            return None

        # Extract project_id from run_id (format: "run-{project_id}")
        project_id = run_id.replace("run-", "")
        return self._run_to_project_plan(run, project_id)

    def _run_to_project_plan(self, run, project_id: str) -> ProjectPlan:
        """Convert an OrchestrationRun to a ProjectPlan."""
        return ProjectPlan(
            id=project_id,
            name=f"Project {project_id}",  # Name wasn't stored, derive from ID
            original_prompt=run.original_prompt,
            workspace_path=run.workspace_path or "",
            status=_run_state_to_project_status(run.state),
            config=ProjectConfig(**run.config_json) if run.config_json else ProjectConfig(),
            created_at=run.created_at,
            started_at=run.started_at,
            completed_at=run.completed_at,
            paused_at=run.paused_at,
        )

    async def list_projects(
        self,
        status: ProjectStatus | None = None,
        limit: int = 50,
    ) -> list[ProjectPlan]:
        """List projects from database."""
        if status:
            # Map status to run states
            state_mapping = {
                ProjectStatus.PLANNING: ["intake", "plan", "task_graph"],
                ProjectStatus.IN_PROGRESS: ["execute", "verify", "synthesize"],
                ProjectStatus.COMPLETED: ["done"],
                ProjectStatus.FAILED: ["failed"],
                ProjectStatus.PAUSED: ["paused"],
                ProjectStatus.CANCELLED: ["cancelled"],
            }
            states = state_mapping.get(status, [status.value])

            projects = []
            for state in states:
                runs = await RunRepository.list_by_status(state, limit=limit)
                for run in runs:
                    project_id = run.id.replace("run-", "")
                    projects.append(self._run_to_project_plan(run, project_id))
            return projects[:limit]
        else:
            # Get all runs
            runs = await RunRepository.list_active()
            return [
                self._run_to_project_plan(run, run.id.replace("run-", ""))
                for run in runs
            ][:limit]

    async def get_active_projects(self) -> list[ProjectPlan]:
        """Get all active (non-terminal) projects from database."""
        runs = await RunRepository.list_active()
        return [
            self._run_to_project_plan(run, run.id.replace("run-", ""))
            for run in runs
        ]

    async def update_project(self, project: ProjectPlan) -> None:
        """Update a project's state in database."""
        run_id = f"run-{project.id}"

        # Map status to run state
        state_mapping = {
            ProjectStatus.PLANNING: "plan",
            ProjectStatus.IN_PROGRESS: "execute",
            ProjectStatus.COMPLETED: "done",
            ProjectStatus.FAILED: "failed",
            ProjectStatus.PAUSED: "paused",
            ProjectStatus.CANCELLED: "cancelled",
            ProjectStatus.BLOCKED: "paused",  # Map blocked to paused
        }
        state = state_mapping.get(project.status, "plan")

        await RunRepository.update_state(run_id, state)

    async def pause_project(self, project_id: str) -> bool:
        """Pause a running project."""
        run_id = f"run-{project_id}"
        run = await RunRepository.get(run_id)

        if not run:
            return False

        if run.state in ("execute", "verify", "synthesize"):
            await RunRepository.update_state(run_id, "paused")
            await RunRepository.set_resume_state(run_id, run.state)
            logger.info(f"Paused project: {project_id}")
            return True
        return False

    async def resume_project(self, project_id: str) -> bool:
        """Resume a paused project."""
        run_id = f"run-{project_id}"
        run = await RunRepository.get(run_id)

        if not run:
            return False

        if run.state == "paused" and run.resume_state:
            await RunRepository.update_state(run_id, run.resume_state)
            await RunRepository.set_resume_state(run_id, None)
            logger.info(f"Resumed project: {project_id}")
            return True
        return False

    async def cancel_project(self, project_id: str) -> bool:
        """Cancel a project."""
        orchestrator_cancelled = False

        # Cancel the orchestrator if running
        if project_id in self._running_orchestrators:
            orchestrator = self._running_orchestrators[project_id]
            if hasattr(orchestrator, 'cancel'):
                orchestrator.cancel()
            del self._running_orchestrators[project_id]
            orchestrator_cancelled = True
            logger.info(f"Cancelled orchestrator for project: {project_id}")

        # Update database
        run_id = f"run-{project_id}"
        success = await RunRepository.update_state(run_id, "cancelled")

        return success or orchestrator_cancelled

    def register_orchestrator(self, project_id: str, orchestrator: Any) -> None:
        """Register a running orchestrator."""
        self._running_orchestrators[project_id] = orchestrator
        logger.info(f"Registered orchestrator for project: {project_id}")

    def unregister_orchestrator(self, project_id: str) -> None:
        """Unregister an orchestrator."""
        self._running_orchestrators.pop(project_id, None)

    def is_orchestrator_running(self, project_id: str) -> bool:
        """Check if orchestrator is running for a project."""
        return project_id in self._running_orchestrators

    async def get_stats(self) -> dict[str, Any]:
        """Get project manager statistics from database."""
        active_runs = await RunRepository.list_active()

        # Count by status
        status_counts: dict[str, int] = {}
        for run in active_runs:
            status = _run_state_to_project_status(run.state).value
            status_counts[status] = status_counts.get(status, 0) + 1

        return {
            "total_active_projects": len(active_runs),
            "running_orchestrators": len(self._running_orchestrators),
            "by_status": status_counts,
        }

    async def cleanup_old_projects(self, max_age_hours: int = 24 * 7) -> int:
        """Remove old completed/cancelled runs from database."""
        # This would typically be done via a background job
        # For now, just return 0 as we keep historical data
        logger.info(f"Cleanup called with max_age_hours={max_age_hours}")
        return 0

    async def get_project_tasks(self, project_id: str) -> list[dict]:
        """Get all tasks for a project."""
        run_id = f"run-{project_id}"
        tasks = await TaskRepository.get_by_run(run_id)
        return [
            {
                "id": task.id,
                "title": task.title,
                "description": task.description,
                "agent_id": task.agent_id,
                "status": task.status,
                "attempt": task.attempt,
                "depends_on": task.depends_on or [],
                "error": task.error,
                "started_at": task.started_at.isoformat() if task.started_at else None,
                "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            }
            for task in tasks
        ]

    async def get_project_logs(
        self,
        project_id: str,
        level: str | None = None,
    ) -> list[dict]:
        """Get all logs for a project."""
        run_id = f"run-{project_id}"
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

    async def get_project_artifacts(self, project_id: str) -> list[dict]:
        """Get all artifacts for a project."""
        run_id = f"run-{project_id}"
        artifacts = await ArtifactRepository.get_by_run(run_id)
        return [
            {
                "id": artifact.id,
                "task_id": artifact.task_id,
                "name": artifact.name,
                "artifact_type": artifact.artifact_type,
                "path": artifact.path,
                "producer_agent": artifact.producer_agent,
                "created_at": artifact.created_at.isoformat(),
            }
            for artifact in artifacts
        ]

    async def get_full_project_state(self, project_id: str) -> dict | None:
        """Get complete project state for resume capability."""
        run_id = f"run-{project_id}"
        return await RunRepository.get_full_state(run_id)


# Global project manager
project_manager = ProjectManager()
