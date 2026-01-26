"""Project manager for tracking autonomous projects."""

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

logger = logging.getLogger(__name__)


class ProjectManager:
    """Manages active autonomous projects."""

    def __init__(self) -> None:
        self._projects: dict[str, ProjectPlan] = {}
        self._running_orchestrators: dict[str, Any] = {}  # Orchestrator objects
        self._lock = asyncio.Lock()

    async def create_project(
        self,
        name: str,
        prompt: str,
        workspace_path: str | Path,
        config: ProjectConfig | None = None,
    ) -> ProjectPlan:
        """Create a new autonomous project."""
        project_id = str(uuid.uuid4())[:8]

        project = ProjectPlan(
            id=project_id,
            name=name,
            original_prompt=prompt,
            workspace_path=str(workspace_path),
            status=ProjectStatus.PLANNING,
            config=config or ProjectConfig(),
        )

        async with self._lock:
            self._projects[project_id] = project

        logger.info(f"Created project: {project_id} - {name}")
        return project

    def get(self, project_id: str) -> ProjectPlan | None:
        """Get a project by ID."""
        return self._projects.get(project_id)

    def list_projects(
        self,
        status: ProjectStatus | None = None,
        limit: int = 50,
    ) -> list[ProjectPlan]:
        """List projects with optional filters."""
        projects = list(self._projects.values())

        if status:
            projects = [p for p in projects if p.status == status]

        # Sort by created time, newest first
        projects.sort(key=lambda p: p.created_at, reverse=True)

        return projects[:limit]

    def get_active_projects(self) -> list[ProjectPlan]:
        """Get all active (non-terminal) projects."""
        active_statuses = (
            ProjectStatus.PLANNING,
            ProjectStatus.IN_PROGRESS,
            ProjectStatus.BLOCKED,
            ProjectStatus.PAUSED,
        )
        return [p for p in self._projects.values() if p.status in active_statuses]

    async def update_project(self, project: ProjectPlan) -> None:
        """Update a project in the registry."""
        async with self._lock:
            self._projects[project.id] = project

    async def pause_project(self, project_id: str) -> bool:
        """Pause a running project."""
        project = self.get(project_id)
        if not project:
            return False

        if project.status == ProjectStatus.IN_PROGRESS:
            project.status = ProjectStatus.PAUSED
            project.paused_at = datetime.now()
            await self.update_project(project)
            logger.info(f"Paused project: {project_id}")
            return True
        return False

    async def resume_project(self, project_id: str) -> bool:
        """Resume a paused project."""
        project = self.get(project_id)
        if not project:
            return False

        if project.status == ProjectStatus.PAUSED:
            project.status = ProjectStatus.IN_PROGRESS
            project.paused_at = None
            await self.update_project(project)
            logger.info(f"Resumed project: {project_id}")
            return True
        return False

    async def cancel_project(self, project_id: str) -> bool:
        """Cancel a project."""
        project = self.get(project_id)
        orchestrator_cancelled = False

        # Cancel the orchestrator if running (even if project not in memory)
        if project_id in self._running_orchestrators:
            orchestrator = self._running_orchestrators[project_id]
            if hasattr(orchestrator, 'cancel'):
                orchestrator.cancel()
            del self._running_orchestrators[project_id]
            orchestrator_cancelled = True
            logger.info(f"Cancelled orchestrator for project: {project_id}")

        if not project:
            # Project not in memory - return True if we at least cancelled the orchestrator
            return orchestrator_cancelled

        project.status = ProjectStatus.CANCELLED
        project.completed_at = datetime.now()
        await self.update_project(project)
        logger.info(f"Cancelled project: {project_id}")
        return True

    def register_orchestrator(self, project_id: str, orchestrator: Any) -> None:
        """Register a running orchestrator.

        Args:
            project_id: The project ID
            orchestrator: The Orchestrator object (has .cancel() method)
        """
        self._running_orchestrators[project_id] = orchestrator
        logger.info(f"Registered orchestrator for project: {project_id}")

    def unregister_orchestrator(self, project_id: str) -> None:
        """Unregister an orchestrator task."""
        self._running_orchestrators.pop(project_id, None)

    def is_orchestrator_running(self, project_id: str) -> bool:
        """Check if orchestrator is running for a project."""
        return project_id in self._running_orchestrators

    def get_stats(self) -> dict[str, Any]:
        """Get project manager statistics."""
        projects = list(self._projects.values())

        return {
            "total_projects": len(projects),
            "active_projects": len(self.get_active_projects()),
            "running_orchestrators": len(self._running_orchestrators),
            "by_status": {
                status.value: len([p for p in projects if p.status == status])
                for status in ProjectStatus
            },
        }

    async def cleanup_old_projects(self, max_age_hours: int = 24 * 7) -> int:
        """Remove old completed/cancelled projects."""
        now = datetime.now()
        to_remove = []

        for project_id, project in self._projects.items():
            if project.status in (ProjectStatus.COMPLETED, ProjectStatus.CANCELLED, ProjectStatus.FAILED):
                if project.completed_at:
                    age_hours = (now - project.completed_at).total_seconds() / 3600
                    if age_hours > max_age_hours:
                        to_remove.append(project_id)

        async with self._lock:
            for project_id in to_remove:
                del self._projects[project_id]

        return len(to_remove)


# Global project manager
project_manager = ProjectManager()
