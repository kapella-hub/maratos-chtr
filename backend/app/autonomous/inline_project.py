"""Inline Project Tracking.

This module tracks inline projects within chat sessions,
integrating with the unified orchestration engine.
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from app.autonomous.engine import RunState
from app.autonomous.inline_orchestrator import (
    InlineOrchestrator,
    get_inline_orchestrator,
    remove_inline_orchestrator,
)
from app.autonomous.planner_schema import ExecutionPlan


class InlineProjectStatus(Enum):
    """Status of an inline project mapped from engine RunState."""
    PLANNING = "planning"
    AWAITING_APPROVAL = "awaiting_approval"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    PAUSED = "paused"
    CANCELLED = "cancelled"
    FAILED = "failed"


def _map_run_state_to_status(state: RunState) -> InlineProjectStatus:
    """Map engine RunState to InlineProjectStatus."""
    mapping = {
        RunState.INTAKE: InlineProjectStatus.PLANNING,
        RunState.PLAN: InlineProjectStatus.PLANNING,
        RunState.TASK_GRAPH: InlineProjectStatus.PLANNING,
        RunState.EXECUTE: InlineProjectStatus.EXECUTING,
        RunState.VERIFY: InlineProjectStatus.VERIFYING,
        RunState.SYNTHESIZE: InlineProjectStatus.EXECUTING,
        RunState.DONE: InlineProjectStatus.COMPLETED,
        RunState.FAILED: InlineProjectStatus.FAILED,
        RunState.PAUSED: InlineProjectStatus.PAUSED,
        RunState.CANCELLED: InlineProjectStatus.CANCELLED,
    }
    return mapping.get(state, InlineProjectStatus.PLANNING)


class InlineProject:
    """Represents an inline project backed by the orchestration engine.

    This is a facade over InlineOrchestrator for backwards compatibility
    with existing code that expects a project object.
    """

    def __init__(
        self,
        session_id: str,
        workspace_path: str = "",
        orchestrator: InlineOrchestrator | None = None,
    ):
        self.session_id = session_id
        self.workspace_path = workspace_path
        self._orchestrator = orchestrator or get_inline_orchestrator(
            session_id, workspace_path
        )
        self._status = InlineProjectStatus.PLANNING
        self.created_at = datetime.utcnow()

    @property
    def status(self) -> InlineProjectStatus:
        """Get current project status."""
        if self._orchestrator and self._orchestrator._run_state:
            state_str = self._orchestrator._run_state.get("state")
            if state_str:
                try:
                    return _map_run_state_to_status(RunState(state_str))
                except ValueError:
                    pass
        return self._status

    @status.setter
    def status(self, value: InlineProjectStatus) -> None:
        """Set project status."""
        self._status = value

    @property
    def is_active(self) -> bool:
        """Check if project is active (not in terminal state)."""
        return self.status not in (
            InlineProjectStatus.COMPLETED,
            InlineProjectStatus.CANCELLED,
            InlineProjectStatus.FAILED,
        )

    @property
    def plan(self) -> ExecutionPlan | None:
        """Get the execution plan if available."""
        if self._orchestrator:
            return self._orchestrator.current_plan
        return None

    @property
    def run_id(self) -> str | None:
        """Get the current run ID."""
        if self._orchestrator:
            return self._orchestrator._run_id
        return None

    def to_dict(self) -> dict:
        """Serialize project state."""
        return {
            "session_id": self.session_id,
            "workspace_path": self.workspace_path,
            "status": self.status.value,
            "is_active": self.is_active,
            "run_id": self.run_id,
            "plan": self.plan.model_dump() if self.plan else None,
            "created_at": self.created_at.isoformat(),
        }


def get_inline_project(session_id: str) -> Optional[InlineProject]:
    """Get the inline project for a session.

    Returns the project if an orchestrator exists for the session,
    otherwise returns None.
    """
    orchestrator = get_inline_orchestrator(session_id, create=False)
    if orchestrator:
        return InlineProject(session_id, orchestrator.workspace_path, orchestrator)
    return None


def create_inline_project(session_id: str, workspace_path: str) -> InlineProject:
    """Create a new inline project.

    This creates a new InlineOrchestrator and wraps it in an InlineProject.
    """
    orchestrator = get_inline_orchestrator(session_id, workspace_path, create=True)
    return InlineProject(session_id, workspace_path, orchestrator)


def delete_inline_project(session_id: str) -> None:
    """Delete an inline project."""
    remove_inline_orchestrator(session_id)
