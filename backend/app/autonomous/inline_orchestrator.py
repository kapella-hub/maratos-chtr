"""Inline Orchestrator - Project mode within chat sessions.

This module provides inline project orchestration using the unified
orchestration engine. It bridges the chat API with the engine, converting
engine events to chat-compatible SSE events.
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, AsyncIterator

from app.autonomous.engine import (
    EngineEvent,
    EngineEventType,
    OrchestrationEngine,
    RunConfig,
    RunContext,
    RunState,
    get_engine,
)
from app.autonomous.planner_schema import ExecutionPlan

logger = logging.getLogger(__name__)


@dataclass
class InlineEvent:
    """Event from inline orchestrator for SSE streaming."""
    type: str
    data: dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_sse(self) -> str:
        """Convert to SSE format compatible with chat API."""
        payload = {"type": self.type, **self.data}
        return f"data: {json.dumps(payload)}\n\n"


class InlineOrchestrator:
    """Orchestrates inline projects within chat sessions using the unified engine.

    This class wraps the OrchestrationEngine to provide a chat-session-aware
    interface for "project mode" orchestration.
    """

    def __init__(
        self,
        session_id: str,
        workspace_path: str = "",
        engine: OrchestrationEngine | None = None,
    ):
        self.session_id = session_id
        self.workspace_path = workspace_path
        self.engine = engine or get_engine()

        # Current run tracking
        self._run_id: str | None = None
        self._run_state: dict | None = None
        self._plan: ExecutionPlan | None = None

        # Project reference for backwards compatibility
        self._project: Any = None

    @property
    def project(self) -> Any:
        """Get the associated project object."""
        return self._project

    @project.setter
    def project(self, value: Any) -> None:
        """Set the associated project object."""
        self._project = value
        if value and hasattr(value, 'workspace_path'):
            self.workspace_path = value.workspace_path

    @property
    def is_active(self) -> bool:
        """Check if there's an active orchestration run."""
        return self._run_id is not None

    @property
    def current_plan(self) -> ExecutionPlan | None:
        """Get the current execution plan."""
        return self._plan

    async def start_project(
        self,
        prompt: str,
        config: RunConfig | None = None,
    ) -> AsyncIterator[InlineEvent]:
        """Start a new inline project from a user prompt.

        This initiates the orchestration engine and streams events
        back as chat-compatible SSE events.
        """
        config = config or RunConfig(
            parallel_tasks=2,  # Conservative for inline mode
            task_timeout_seconds=180.0,
            run_verification=True,
        )

        yield InlineEvent(
            type="project_started",
            data={
                "session_id": self.session_id,
                "workspace_path": self.workspace_path,
            },
        )

        try:
            async for event in self.engine.run(
                prompt=prompt,
                workspace_path=self.workspace_path,
                session_id=self.session_id,
                config=config,
            ):
                self._run_id = event.run_id

                # Convert engine events to inline events
                async for inline_event in self._convert_event(event):
                    yield inline_event

                # Track state for resume capability
                self._run_state = self.engine.get_run_state(event.run_id)

        except Exception as e:
            logger.exception(f"Inline project failed: {e}")
            yield InlineEvent(type="project_error", data={"error": str(e)})

        finally:
            self._run_id = None

    async def _convert_event(self, event: EngineEvent) -> AsyncIterator[InlineEvent]:
        """Convert an engine event to inline events."""
        etype = event.type

        # State changes
        if etype == EngineEventType.RUN_STATE:
            state = event.data.get("state")
            yield InlineEvent(
                type="run_state",
                data={
                    "state": state,
                    "run_id": event.run_id,
                },
            )

            # Map to orchestrating flag for frontend compatibility
            if state in ("plan", "task_graph", "execute"):
                yield InlineEvent(type="orchestrating", data={"value": True})
            elif state in ("done", "failed", "cancelled"):
                yield InlineEvent(type="orchestrating", data={"value": False})

        # Planning events
        elif etype == EngineEventType.PLANNING_STARTED:
            yield InlineEvent(type="planning_started", data={})

        elif etype == EngineEventType.PLANNING_PROGRESS:
            yield InlineEvent(
                type="planning_progress",
                data={"progress": event.data.get("progress", 0)},
            )

        elif etype == EngineEventType.PLANNING_COMPLETED:
            plan = event.data.get("plan")
            if isinstance(plan, ExecutionPlan):
                self._plan = plan
                plan_data = plan.model_dump()
            else:
                plan_data = plan
            yield InlineEvent(
                type="planning_completed",
                data={
                    "plan": plan_data,
                    "task_count": event.data.get("task_count", 0),
                },
            )

        # Task graph events
        elif etype == EngineEventType.TASK_GRAPH_BUILT:
            yield InlineEvent(
                type="task_graph_built",
                data={
                    "task_count": event.data.get("task_count"),
                    "levels": event.data.get("levels"),
                },
            )

        # Task execution events - map to subagent format for frontend
        elif etype == EngineEventType.TASK_STARTED:
            yield InlineEvent(
                type="subagent",
                data={
                    "task_id": event.data.get("task_id"),
                    "agent_id": event.data.get("agent_id"),
                    "title": event.data.get("title"),
                    "status": "running",
                    "attempt": event.data.get("attempt", 1),
                },
            )

        elif etype == EngineEventType.TASK_PROGRESS:
            yield InlineEvent(
                type="task_progress",
                data={
                    "task_id": event.data.get("task_id"),
                    "progress": event.data.get("progress", 0),
                },
            )

        elif etype == EngineEventType.TASK_OUTPUT:
            yield InlineEvent(
                type="task_output",
                data={
                    "task_id": event.data.get("task_id"),
                    "output": event.data.get("output"),
                },
            )

        elif etype == EngineEventType.TASK_COMPLETED:
            yield InlineEvent(
                type="subagent",
                data={
                    "task_id": event.data.get("task_id"),
                    "status": "completed",
                },
            )
            yield InlineEvent(
                type="subagent_result",
                data={
                    "task_id": event.data.get("task_id"),
                    "result": event.data.get("result"),
                    "artifacts": event.data.get("artifacts"),
                },
            )

        elif etype == EngineEventType.TASK_FAILED:
            yield InlineEvent(
                type="subagent",
                data={
                    "task_id": event.data.get("task_id"),
                    "status": "failed",
                    "error": event.data.get("error"),
                },
            )

        elif etype == EngineEventType.TASK_RETRYING:
            yield InlineEvent(
                type="task_retrying",
                data={
                    "task_id": event.data.get("task_id"),
                    "reason": event.data.get("reason"),
                    "next_attempt": event.data.get("next_attempt"),
                },
            )

        # Verification events
        elif etype == EngineEventType.VERIFICATION_STARTED:
            yield InlineEvent(type="verification_started", data={})

        elif etype == EngineEventType.VERIFICATION_RESULT:
            yield InlineEvent(
                type="verification_result",
                data={
                    "task_id": event.data.get("task_id"),
                    "criterion_id": event.data.get("criterion_id"),
                    "passed": event.data.get("passed"),
                },
            )

        elif etype == EngineEventType.VERIFICATION_COMPLETED:
            yield InlineEvent(
                type="verification_completed",
                data={"passed": event.data.get("passed")},
            )

        # Artifact events
        elif etype == EngineEventType.ARTIFACT_CREATED:
            yield InlineEvent(
                type="artifact_created",
                data={
                    "task_id": event.data.get("task_id"),
                    "name": event.data.get("artifact_name"),
                    "type": event.data.get("artifact_type"),
                },
            )

        # Synthesis events
        elif etype == EngineEventType.SYNTHESIS_COMPLETED:
            yield InlineEvent(
                type="synthesis_completed",
                data={"results": event.data.get("results")},
            )

        # Error events
        elif etype == EngineEventType.RUN_ERROR:
            yield InlineEvent(
                type="project_error",
                data={"error": event.data.get("error")},
            )

    async def approve_plan(self) -> AsyncIterator[InlineEvent]:
        """Approve the current plan and start execution.

        Called when user approves the plan in project mode.
        """
        if not self._plan:
            yield InlineEvent(type="error", data={"message": "No plan to approve"})
            return

        yield InlineEvent(type="plan_approved", data={})

        # Resume execution from the plan
        config = RunConfig(
            parallel_tasks=2,
            run_verification=True,
        )

        async for event in self.engine.run(
            prompt=self._plan.original_prompt,
            workspace_path=self.workspace_path,
            session_id=self.session_id,
            config=config,
            existing_plan=self._plan,
        ):
            async for inline_event in self._convert_event(event):
                yield inline_event

    async def pause_project(self) -> AsyncIterator[InlineEvent]:
        """Pause the current project execution."""
        if not self._run_id:
            yield InlineEvent(type="error", data={"message": "No active project"})
            return

        success = await self.engine.pause(self._run_id)
        if success:
            self._run_state = self.engine.get_run_state(self._run_id)
            yield InlineEvent(type="project_paused", data={"run_id": self._run_id})
        else:
            yield InlineEvent(type="error", data={"message": "Cannot pause project"})

    async def resume_project(self) -> AsyncIterator[InlineEvent]:
        """Resume a paused project."""
        if not self._run_id:
            yield InlineEvent(type="error", data={"message": "No active project"})
            return

        yield InlineEvent(type="project_resuming", data={})

        async for event in self.engine.resume(self._run_id):
            async for inline_event in self._convert_event(event):
                yield inline_event

    async def cancel_project(self) -> AsyncIterator[InlineEvent]:
        """Cancel the current project."""
        if self._run_id:
            await self.engine.cancel(self._run_id)

        self._run_id = None
        self._plan = None
        self._run_state = None

        yield InlineEvent(type="project_cancelled", data={})

    async def adjust_plan(self, adjustments: dict) -> AsyncIterator[InlineEvent]:
        """Adjust the current plan based on user feedback.

        Args:
            adjustments: Dict with adjustments like:
                - add_tasks: List of tasks to add
                - remove_tasks: List of task IDs to remove
                - modify_tasks: Dict of task_id -> modifications
        """
        if not self._plan:
            yield InlineEvent(type="error", data={"message": "No plan to adjust"})
            return

        # Apply adjustments to plan
        tasks = list(self._plan.tasks)

        # Remove tasks
        if "remove_tasks" in adjustments:
            tasks = [t for t in tasks if t.id not in adjustments["remove_tasks"]]

        # Modify tasks
        if "modify_tasks" in adjustments:
            for task_id, mods in adjustments["modify_tasks"].items():
                for i, task in enumerate(tasks):
                    if task.id == task_id:
                        task_dict = task.model_dump()
                        task_dict.update(mods)
                        from app.autonomous.planner_schema import PlannedTask
                        tasks[i] = PlannedTask.model_validate(task_dict)

        # Add tasks
        if "add_tasks" in adjustments:
            from app.autonomous.planner_schema import PlannedTask
            for task_data in adjustments["add_tasks"]:
                tasks.append(PlannedTask.model_validate(task_data))

        # Create new plan
        plan_data = self._plan.model_dump()
        plan_data["tasks"] = [t.model_dump() for t in tasks]
        self._plan = ExecutionPlan.model_validate(plan_data)

        yield InlineEvent(
            type="plan_adjusted",
            data={
                "plan": self._plan.model_dump(),
                "task_count": len(self._plan.tasks),
            },
        )

    def get_state_for_persistence(self) -> dict | None:
        """Get the current state for persistence (resume support)."""
        return self._run_state

    async def detect_and_plan(
        self,
        prompt: str,
        config: Any = None,
    ) -> AsyncIterator[InlineEvent]:
        """Detect if project mode is appropriate and create a plan.

        This method combines detection and planning into a single flow,
        emitting planning events that the chat UI can display.

        Args:
            prompt: The user's message to analyze and plan
            config: Optional project configuration
        """
        from app.autonomous.detection import project_detector, DetectionResult

        # Emit detection start
        yield InlineEvent(
            type="project_detected",
            data={
                "session_id": self.session_id,
                "prompt": prompt[:200],
            },
        )

        # Start the project (which includes planning)
        run_config = RunConfig(
            parallel_tasks=2,
            task_timeout_seconds=180.0,
            run_verification=True,
        )

        async for event in self.start_project(prompt, run_config):
            yield event

            # After planning completes, emit awaiting approval
            if event.type == "planning_completed":
                yield InlineEvent(
                    type="awaiting_approval",
                    data={
                        "plan": event.data.get("plan"),
                        "message": "Review the plan above. Reply 'approve' to start, or describe changes.",
                    },
                )

    async def _handle_interrupt(self, message: str) -> AsyncIterator[InlineEvent]:
        """Handle an interrupt message during execution.

        Args:
            message: The interrupt message from the user
        """
        message_lower = message.lower().strip()

        # Check for pause/stop commands
        if message_lower in ("pause", "hold", "wait", "stop"):
            async for event in self.pause_project():
                yield event
            return

        # Check for cancel commands
        if message_lower in ("cancel", "abort", "quit", "exit"):
            async for event in self.cancel_project():
                yield event
            return

        # Otherwise, emit a message that we received the interrupt
        yield InlineEvent(
            type="interrupt_received",
            data={
                "message": message,
                "note": "Project is currently executing. Use 'pause' to pause, 'cancel' to abort.",
            },
        )


# =============================================================================
# Session Registry
# =============================================================================

# Active inline orchestrators by session
_orchestrators: dict[str, InlineOrchestrator] = {}


def get_inline_orchestrator(
    session_id: str,
    workspace_path: str = "",
    create: bool = True,
) -> InlineOrchestrator | None:
    """Get or create an inline orchestrator for a session."""
    if session_id in _orchestrators:
        return _orchestrators[session_id]

    if create:
        orchestrator = InlineOrchestrator(session_id, workspace_path)
        _orchestrators[session_id] = orchestrator
        return orchestrator

    return None


def remove_inline_orchestrator(session_id: str) -> None:
    """Remove an inline orchestrator from the registry."""
    _orchestrators.pop(session_id, None)


# =============================================================================
# Action Handler (for chat API)
# =============================================================================

async def handle_project_action(
    session_id: str,
    action: str,
    data: dict | None = None,
) -> AsyncIterator[InlineEvent]:
    """Handle a project action request from the chat API.

    Args:
        session_id: The chat session ID
        action: Action to perform (approve, pause, resume, cancel, adjust)
        data: Optional action data
    """
    orchestrator = get_inline_orchestrator(session_id, create=False)

    if not orchestrator:
        yield InlineEvent(
            type="error",
            data={"message": f"No active project for session {session_id}"},
        )
        return

    data = data or {}

    if action == "approve":
        async for event in orchestrator.approve_plan():
            yield event

    elif action == "pause":
        async for event in orchestrator.pause_project():
            yield event

    elif action == "resume":
        async for event in orchestrator.resume_project():
            yield event

    elif action == "cancel":
        async for event in orchestrator.cancel_project():
            yield event
        remove_inline_orchestrator(session_id)

    elif action == "adjust":
        async for event in orchestrator.adjust_plan(data.get("adjustments", {})):
            yield event

    else:
        yield InlineEvent(
            type="error",
            data={"message": f"Unknown project action: {action}"},
        )
