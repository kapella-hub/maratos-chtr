"""Unified Orchestration Engine.

This module implements the canonical orchestration state machine that powers
both inline "project mode" from chat and autonomous API-driven project runs.

State Machine:
    INTAKE -> PLAN -> TASK_GRAPH -> EXECUTE -> VERIFY -> SYNTHESIZE -> DONE/FAILED

The engine supports:
- Deterministic multi-pass planning/execution/verification
- DAG-based task dependencies
- Streaming progress via SSE events
- Interrupt and resume capabilities
"""

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, AsyncIterator, Callable, Iterator

from app.autonomous.planner_schema import (
    AcceptanceCriterion,
    ExecutionPlan,
    PlannedTask,
    PlanMetadata,
    TaskInput,
    TaskOutput,
)
from app.autonomous.task_graph import TaskGraph, TaskNode, TaskNodeStatus

logger = logging.getLogger(__name__)


# =============================================================================
# Run State Machine
# =============================================================================

class RunState(str, Enum):
    """Canonical run states for the orchestration engine."""
    INTAKE = "intake"           # Receiving and validating input
    BRAINSTORM = "brainstorm"   # Multi-agent brainstorming
    PLAN = "plan"               # Planning tasks with architect/planner
    TASK_GRAPH = "task_graph"   # Building and validating task DAG
    EXECUTE = "execute"         # Running tasks
    VERIFY = "verify"           # Final verification pass
    SYNTHESIZE = "synthesize"   # Generating final summary/output
    DONE = "done"               # Successfully completed
    FAILED = "failed"           # Failed with error
    PAUSED = "paused"           # Paused by user
    CANCELLED = "cancelled"     # Cancelled by user


# Valid state transitions
STATE_TRANSITIONS: dict[RunState, set[RunState]] = {
    RunState.INTAKE: {RunState.BRAINSTORM, RunState.PLAN, RunState.FAILED, RunState.CANCELLED},
    RunState.BRAINSTORM: {RunState.PLAN, RunState.FAILED, RunState.CANCELLED},
    RunState.PLAN: {RunState.TASK_GRAPH, RunState.FAILED, RunState.CANCELLED, RunState.PAUSED},
    RunState.TASK_GRAPH: {RunState.EXECUTE, RunState.FAILED, RunState.CANCELLED},
    RunState.EXECUTE: {RunState.VERIFY, RunState.FAILED, RunState.CANCELLED, RunState.PAUSED},
    RunState.VERIFY: {RunState.SYNTHESIZE, RunState.EXECUTE, RunState.FAILED},  # Can loop back to EXECUTE
    RunState.SYNTHESIZE: {RunState.DONE, RunState.FAILED},
    RunState.DONE: set(),
    RunState.FAILED: set(),
    RunState.PAUSED: {RunState.PLAN, RunState.EXECUTE, RunState.CANCELLED},  # Resume to previous state
    RunState.CANCELLED: set(),
}


# =============================================================================
# SSE Event Types
# =============================================================================

class EngineEventType(str, Enum):
    """Event types emitted by the orchestration engine."""
    # State machine events
    RUN_STATE = "run_state"
    RUN_ERROR = "run_error"

    # Planning events
    PLANNING_STARTED = "planning_started"
    PLANNING_PROGRESS = "planning_progress"
    PLANNING_COMPLETED = "planning_completed"

    # Brainstorming events
    BRAINSTORMING_STARTED = "brainstorming_started"
    BRAINSTORMING_PROGRESS = "brainstorming_progress"
    BRAINSTORMING_COMPLETED = "brainstorming_completed"
    BRAINSTORMING_VISUALIZATION = "brainstorming_visualization"

    # Task graph events
    TASK_GRAPH_BUILT = "task_graph_built"
    TASK_GRAPH_VALIDATED = "task_graph_validated"

    # Task execution events
    TASK_STARTED = "task_started"
    TASK_PROGRESS = "task_progress"
    TASK_OUTPUT = "task_output"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    TASK_RETRYING = "task_retrying"
    TASK_SKIPPED = "task_skipped"

    # Verification events
    VERIFICATION_STARTED = "verification_started"
    VERIFICATION_RESULT = "verification_result"
    VERIFICATION_COMPLETED = "verification_completed"

    # Artifact events
    ARTIFACT_CREATED = "artifact_created"

    # Synthesis events
    SYNTHESIS_STARTED = "synthesis_started"
    SYNTHESIS_COMPLETED = "synthesis_completed"

    # Control events
    PAUSED = "paused"
    RESUMED = "resumed"
    CANCELLED = "cancelled"

    # Human-in-the-loop events
    APPROVAL_REQUESTED = "approval_requested"
    APPROVAL_RECEIVED = "approval_received"
    PLAN_APPROVAL_REQUESTED = "plan_approval_requested"


@dataclass
class EngineEvent:
    """An event emitted by the orchestration engine."""
    type: EngineEventType
    run_id: str
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_sse(self) -> str:
        """Format as Server-Sent Event."""
        payload = {
            "type": self.type.value,
            "run_id": self.run_id,
            "timestamp": self.timestamp.isoformat(),
            **self.data,
        }
        
        def _encoder(obj):
            if hasattr(obj, "model_dump"):
                return obj.model_dump()
            if hasattr(obj, "dict"):
                return obj.dict()
            if isinstance(obj, datetime):
                return obj.isoformat()
            raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

        return f"data: {json.dumps(payload, default=_encoder)}\n\n"

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "type": self.type.value,
            "run_id": self.run_id,
            "data": self.data,
            "timestamp": self.timestamp.isoformat(),
        }


# =============================================================================
# Run Context - State and Configuration
# =============================================================================

@dataclass
class RunConfig:
    """Configuration for an orchestration run."""
    # Execution settings
    parallel_tasks: int = 3
    task_timeout_seconds: float = 300.0
    max_task_retries: int = 3

    # Verification settings
    run_verification: bool = True
    fail_fast: bool = False

    # Planning settings
    planner_model: str = ""  # Empty = use default
    planner_model: str = ""  # Empty = use default
    planning_timeout_seconds: float = 120.0
    auto_approve: bool = True # Default to True to unblock execution until UI catch-up

    # Resume settings
    resume_from_state: dict | None = None

    # Callbacks (for custom behavior)
    on_state_change: Callable[[RunState, RunState], None] | None = None


@dataclass
class RunContext:
    """Runtime context for an orchestration run."""
    run_id: str
    config: RunConfig
    state: RunState = RunState.INTAKE

    # Input
    original_prompt: str = ""
    workspace_path: str | None = None
    session_id: str | None = None  # For inline mode
    
    # Generic context data (e.g. brainstorm outputs)
    context_data: dict[str, Any] = field(default_factory=dict)

    # Plan and graph
    plan: ExecutionPlan | None = None
    graph: TaskGraph | None = None

    # Timing
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None

    # Error tracking
    error: str | None = None
    error_details: dict | None = None

    # Pause/Resume
    paused_at: datetime | None = None
    resume_state: RunState | None = None  # State to resume to

    # Event queue for streaming
    _event_queue: asyncio.Queue | None = field(default=None, repr=False)

    # Human-in-the-loop state
    approval_events: dict[str, asyncio.Event] = field(default_factory=dict)
    approval_decisions: dict[str, bool] = field(default_factory=dict)

    def __post_init__(self):
        self._event_queue = asyncio.Queue()

    @property
    def duration_ms(self) -> float | None:
        """Get run duration in milliseconds."""
        if self.completed_at:
            return (self.completed_at - self.started_at).total_seconds() * 1000
        return None

    def can_transition_to(self, new_state: RunState) -> bool:
        """Check if transition to new state is valid."""
        return new_state in STATE_TRANSITIONS.get(self.state, set())

    def transition_to(self, new_state: RunState) -> None:
        """Transition to a new state."""
        if not self.can_transition_to(new_state):
            raise ValueError(
                f"Invalid state transition: {self.state.value} -> {new_state.value}"
            )
        old_state = self.state
        self.state = new_state

        if self.config.on_state_change:
            self.config.on_state_change(old_state, new_state)

        if new_state in (RunState.DONE, RunState.FAILED, RunState.CANCELLED):
            self.completed_at = datetime.utcnow()

    def to_dict(self) -> dict:
        """Serialize context for persistence."""
        return {
            "run_id": self.run_id,
            "state": self.state.value,
            "original_prompt": self.original_prompt,
            "workspace_path": self.workspace_path,
            "session_id": self.session_id,
            "context_data": self.context_data,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error": self.error,
            "error_details": self.error_details,
            "paused_at": self.paused_at.isoformat() if self.paused_at else None,
            "resume_state": self.resume_state.value if self.resume_state else None,
            "plan": self.plan.model_dump() if self.plan else None,
            "graph_state": self.graph.to_dict() if self.graph else None,
        }

    @classmethod
    def from_dict(cls, data: dict, config: RunConfig | None = None) -> "RunContext":
        """Restore context from serialized form."""
        ctx = cls(
            run_id=data["run_id"],
            config=config or RunConfig(),
            state=RunState(data["state"]),
            original_prompt=data.get("original_prompt", ""),
            workspace_path=data.get("workspace_path"),
            session_id=data.get("session_id"),
            context_data=data.get("context_data", {}),
        )
        ctx.started_at = datetime.fromisoformat(data["started_at"])
        if data.get("completed_at"):
            ctx.completed_at = datetime.fromisoformat(data["completed_at"])
        ctx.error = data.get("error")
        ctx.error_details = data.get("error_details")
        if data.get("paused_at"):
            ctx.paused_at = datetime.fromisoformat(data["paused_at"])
        if data.get("resume_state"):
            ctx.resume_state = RunState(data["resume_state"])

        # Restore plan
        if data.get("plan"):
            ctx.plan = ExecutionPlan.model_validate(data["plan"])
            ctx.graph = TaskGraph(ctx.plan)
            if data.get("graph_state"):
                ctx.graph.restore_state(data["graph_state"])

        return ctx


# =============================================================================
# Orchestration Engine
# =============================================================================

class OrchestrationEngine:
    """Unified orchestration engine for project execution.

    This engine implements the canonical state machine:
    INTAKE -> PLAN -> TASK_GRAPH -> EXECUTE -> VERIFY -> SYNTHESIZE -> DONE/FAILED

    It supports both inline chat orchestration and autonomous API-driven runs.
    """

    def __init__(
        self,
        planner: "PlannerProtocol | None" = None,
        executor: "ExecutorProtocol | None" = None,
        verifier: "VerifierProtocol | None" = None,
    ):
        """Initialize the engine.

        Args:
            planner: Custom planner implementation (uses default if None)
            executor: Custom executor implementation (uses default if None)
            verifier: Custom verifier implementation (uses default if None)
        """
        self.planner = planner or DefaultPlanner()
        self.executor = executor or DefaultExecutor()
        self.verifier = verifier or DefaultVerifier()

        self._active_runs: dict[str, RunContext] = {}

    async def run(
        self,
        prompt: str,
        workspace_path: str | None = None,
        session_id: str | None = None,
        config: RunConfig | None = None,
        existing_plan: ExecutionPlan | None = None,
    ) -> AsyncIterator[EngineEvent]:
        """Execute an orchestration run.

        Args:
            prompt: The original user request
            workspace_path: Optional workspace directory
            session_id: Optional session ID for inline mode
            config: Run configuration
            existing_plan: Skip planning and use this plan directly

        Yields:
            EngineEvent objects for SSE streaming
        """
        config = config or RunConfig()
        run_id = f"run-{uuid.uuid4().hex[:12]}"

        # Initialize or restore context
        if config.resume_from_state:
            ctx = RunContext.from_dict(config.resume_from_state, config)
            run_id = ctx.run_id
            logger.info(f"Resuming run {run_id} from state {ctx.state.value}")
        else:
            ctx = RunContext(
                run_id=run_id,
                config=config,
                original_prompt=prompt,
                workspace_path=workspace_path,
                session_id=session_id,
            )

        self._active_runs[run_id] = ctx

        try:
            async for event in self._run_state_machine(ctx, existing_plan):
                yield event
        finally:
            self._active_runs.pop(run_id, None)

    async def _run_state_machine(
        self,
        ctx: RunContext,
        existing_plan: ExecutionPlan | None = None,
    ) -> AsyncIterator[EngineEvent]:
        """Execute the state machine."""

        # INTAKE
        if ctx.state == RunState.INTAKE:
            yield self._emit(ctx, EngineEventType.RUN_STATE, state="intake")

            if not ctx.original_prompt.strip():
                for event in self._fail(ctx, "Empty prompt provided"):
                    yield event
                return

            ctx.transition_to(RunState.BRAINSTORM)

        # BRAINSTORM
        if ctx.state == RunState.BRAINSTORM:
            yield self._emit(ctx, EngineEventType.RUN_STATE, state="brainstorm")
            
            try:
                from app.autonomous.squads import SquadFactory, BrainstormingSession
                
                # Check directly if we should brainstorm
                if SquadFactory.analyze_task_complexity(ctx.original_prompt):
                    session = BrainstormingSession(
                        run_id=ctx.run_id,
                        prompt=ctx.original_prompt,
                        workspace_path=ctx.workspace_path
                    )
                    
                    async for event in session.run():
                        yield event
                        if event.type == EngineEventType.BRAINSTORMING_COMPLETED:
                            # Store RFCs for the Planner to see
                            ctx.context_data["brainstorm_rfcs"] = event.data.get("rfcs", [])
                
                ctx.transition_to(RunState.PLAN)
                
            except Exception as e:
                logger.error(f"Brainstorming failed: {e}")
                # Don't fail the run, just proceed to planning without RFCs
                ctx.transition_to(RunState.PLAN)

        # PLAN
        if ctx.state == RunState.PLAN:
            yield self._emit(ctx, EngineEventType.RUN_STATE, state="plan")
            yield self._emit(ctx, EngineEventType.PLANNING_STARTED)

            try:
                if existing_plan:
                    ctx.plan = existing_plan
                else:
                    async for event in self.planner.create_plan(ctx):
                        yield event
                        if event.type == EngineEventType.PLANNING_COMPLETED:
                            ctx.plan = event.data.get("plan")

                if not ctx.plan:
                    for event in self._fail(ctx, "Planning failed to produce a plan"):
                        yield event
                    return

                yield self._emit(
                    ctx,
                    EngineEventType.PLANNING_COMPLETED,
                    plan=ctx.plan.model_dump(),
                    task_count=len(ctx.plan.tasks),
                )

                # Emit approval request
                yield self._emit(
                    ctx,
                    EngineEventType.PLAN_APPROVAL_REQUESTED,
                    plan=ctx.plan.model_dump()
                )
                
                if ctx.config.auto_approve:
                    # Auto-proceed to task graph
                    logger.info("Auto-approving plan based on config.")
                    ctx.transition_to(RunState.TASK_GRAPH)
                else:
                    # Pause for manual approval
                    ctx.resume_state = RunState.TASK_GRAPH
                    ctx.transition_to(RunState.PAUSED)
                    yield self._emit(ctx, EngineEventType.PAUSED)
                    return

                # ctx.transition_to(RunState.TASK_GRAPH)

            except Exception as e:
                logger.exception(f"Planning failed: {e}")
                for event in self._fail(ctx, f"Planning failed: {e}"):
                    yield event
                return

        # TASK_GRAPH
        if ctx.state == RunState.TASK_GRAPH:
            yield self._emit(ctx, EngineEventType.RUN_STATE, state="task_graph")

            try:
                ctx.graph = TaskGraph(ctx.plan)
                yield self._emit(
                    ctx,
                    EngineEventType.TASK_GRAPH_BUILT,
                    task_count=len(ctx.graph.nodes),
                    levels=ctx.graph.execution_levels(),
                )

                # Validate graph
                yield self._emit(
                    ctx,
                    EngineEventType.TASK_GRAPH_VALIDATED,
                    root_tasks=[t.task_id for t in ctx.graph.get_ready_tasks()],
                )
                ctx.transition_to(RunState.EXECUTE)

            except Exception as e:
                logger.exception(f"Task graph construction failed: {e}")
                for event in self._fail(ctx, f"Invalid task graph: {e}"):
                    yield event
                return

        # EXECUTE
        if ctx.state == RunState.EXECUTE:
            yield self._emit(ctx, EngineEventType.RUN_STATE, state="execute")

            try:
                async for event in self._execute_tasks(ctx):
                    yield event

                    # Check for pause
                    if ctx.state == RunState.PAUSED:
                        return

                    # Check fail-fast
                    if ctx.config.fail_fast and ctx.graph.has_failures:
                        for event in self._fail(ctx, "Fail-fast triggered by task failure"):
                            yield event
                        return

                if ctx.graph.has_failures and not ctx.graph.is_complete:
                    for event in self._fail(ctx, "Some tasks failed"):
                        yield event
                    return

                ctx.transition_to(RunState.VERIFY)

            except Exception as e:
                logger.exception(f"Execution failed: {e}")
                for event in self._fail(ctx, f"Execution failed: {e}"):
                    yield event
                return

        # VERIFY
        if ctx.state == RunState.VERIFY:
            yield self._emit(ctx, EngineEventType.RUN_STATE, state="verify")

            if ctx.config.run_verification:
                yield self._emit(ctx, EngineEventType.VERIFICATION_STARTED)

                async for event in self.verifier.verify(ctx):
                    yield event

                # Check if verification requires re-execution
                if event.type == EngineEventType.VERIFICATION_COMPLETED:
                    if not event.data.get("passed", True):
                        if event.data.get("retry_tasks"):
                            # Reset specific tasks and go back to execute
                            for task_id in event.data["retry_tasks"]:
                                if ctx.graph.can_retry(task_id):
                                    ctx.graph.retry_task(task_id)
                            ctx.transition_to(RunState.EXECUTE)
                            async for ev in self._run_state_machine(ctx):
                                yield ev
                            return

            yield self._emit(ctx, EngineEventType.VERIFICATION_COMPLETED, passed=True)
            ctx.transition_to(RunState.SYNTHESIZE)

        # SYNTHESIZE
        if ctx.state == RunState.SYNTHESIZE:
            yield self._emit(ctx, EngineEventType.RUN_STATE, state="synthesize")
            yield self._emit(ctx, EngineEventType.SYNTHESIS_STARTED)

            # Collect results
            results = {
                "tasks_completed": len(ctx.graph.get_completed_tasks()),
                "tasks_failed": len(ctx.graph.get_failed_tasks()),
                "artifacts": {
                    node.task_id: node.artifacts
                    for node in ctx.graph.nodes.values()
                    if node.artifacts
                },
                "duration_ms": ctx.duration_ms,
            }

            yield self._emit(ctx, EngineEventType.SYNTHESIS_COMPLETED, results=results)
            ctx.transition_to(RunState.DONE)

        # DONE
        if ctx.state == RunState.DONE:
            yield self._emit(
                ctx,
                EngineEventType.RUN_STATE,
                state="done",
                summary={
                    "status": "completed",
                    "tasks": ctx.graph.get_status_summary() if ctx.graph else {},
                    "duration_ms": ctx.duration_ms,
                },
            )

    async def _execute_tasks(self, ctx: RunContext) -> AsyncIterator[EngineEvent]:
        """Execute tasks from the graph with parallel support."""
        graph = ctx.graph
        running: dict[str, asyncio.Task] = {}
        queue = asyncio.Queue()

        while not graph.is_complete:
            # Check for pause
            if ctx.state == RunState.PAUSED:
                # Cancel running tasks gracefully
                for task in running.values():
                    task.cancel()
                return

            # Start ready tasks up to parallel limit
            ready = graph.get_ready_tasks()
            slots_available = ctx.config.parallel_tasks - len(running)

            for node in ready[:slots_available]:
                task_id = node.task_id
                graph.mark_running(task_id)

                yield self._emit(
                    ctx,
                    EngineEventType.TASK_STARTED,
                    task_id=task_id,
                    agent_id=node.task.agent_id,
                    title=node.task.title,
                    attempt=node.attempt,
                )

                # Create async task for execution
                running[task_id] = asyncio.create_task(
                    self._execute_single_task(ctx, node, queue)
                )

            if not running and not graph.get_ready_tasks():
                # No tasks running and none ready - might be blocked
                break

            # Wait for event or task completion
            get_event_task = asyncio.create_task(queue.get())
            wait_set = set(running.values()) | {get_event_task}
            
            done, _ = await asyncio.wait(wait_set, return_when=asyncio.FIRST_COMPLETED)
            
            # Handle event
            if get_event_task in done:
                event = get_event_task.result()
                yield event
            else:
                get_event_task.cancel()

            # Handle finished tasks
            finished_ids = []
            for tid, t in running.items():
                if t.done():
                    finished_ids.append(tid)
                    if not t.cancelled() and t.exception():
                        logger.error(f"Task {tid} crashed", exc_info=t.exception())
                        # Try to fail the task if not already
                        if not graph.nodes[tid].status == "failed":
                             graph.mark_failed(tid, str(t.exception()))
                             yield self._emit(
                                 ctx,
                                 EngineEventType.TASK_FAILED,
                                 task_id=tid,
                                 error=str(t.exception())
                             )

            for tid in finished_ids:
                del running[tid]

            # Drain remaining events to prevent lag
            while not queue.empty():
                yield queue.get_nowait()

    async def _execute_single_task(
        self,
        ctx: RunContext,
        node: TaskNode,
        queue: asyncio.Queue,
    ) -> None:
        """Execute a single task and put events in queue."""
        task_id = node.task_id

        try:
            # Emit start event - REMOVED (Handled by _execute_tasks loop)
            # await queue.put(
            #     self._emit(
            #         ctx,
            #         EngineEventType.TASK_STARTED,
            #         task_id=task_id,
            #         title=node.task.title,
            #         agent_id=node.task.agent_id
            #     )
            # )

            # Get input artifacts from dependencies
            inputs = ctx.graph.get_input_artifacts(task_id)

            # Execute via executor
            result = await self.executor.execute_task(
                ctx=ctx,
                node=node,
                inputs=inputs,
                on_progress=lambda p: queue.put_nowait(
                    self._emit(ctx, EngineEventType.TASK_PROGRESS, task_id=task_id, progress=p)
                ),
                on_output=lambda o: queue.put_nowait(
                    self._emit(ctx, EngineEventType.TASK_OUTPUT, task_id=task_id, output=o)
                ),
            )

            # Handle result
            if result.get("success"):
                # Run acceptance criteria if any
                ctx.graph.mark_verifying(task_id)

                verification_passed = True
                for criterion in node.task.acceptance:
                    passed = await self._check_acceptance(ctx, node, criterion, queue) # Pass queue
                    node.verification_results[criterion.id] = passed
                    await queue.put(
                        self._emit(
                            ctx,
                            EngineEventType.VERIFICATION_RESULT,
                            task_id=task_id,
                            criterion_id=criterion.id,
                            passed=passed,
                        )
                    )
                    if criterion.required and not passed:
                        verification_passed = False

                if verification_passed:
                    ctx.graph.mark_completed(task_id, result)
                    await queue.put(
                        self._emit(
                            ctx,
                            EngineEventType.TASK_COMPLETED,
                            task_id=task_id,
                            agent_id=node.task.agent_id,
                            result=result,
                            artifacts=node.artifacts,
                        )
                    )

                    # Emit artifact events
                    for name, value in node.artifacts.items():
                        await queue.put(
                            self._emit(
                                ctx,
                                EngineEventType.ARTIFACT_CREATED,
                                task_id=task_id,
                                artifact_name=name,
                                artifact_type=type(value).__name__,
                            )
                        )
                else:
                    # Verification failed - retry or fail
                    if ctx.graph.can_retry(task_id):
                        ctx.graph.retry_task(task_id)
                        await queue.put(
                            self._emit(
                                ctx,
                                EngineEventType.TASK_RETRYING,
                                task_id=task_id,
                                title=node.task.title,
                                agent_id=node.task.agent_id,
                                reason="Verification failed",
                                next_attempt=node.attempt + 1,
                            )
                        )
                    else:
                        ctx.graph.mark_failed(task_id, "Verification failed after max attempts")
                        await queue.put(
                            self._emit(
                                ctx,
                                EngineEventType.TASK_FAILED,
                                task_id=task_id,
                                title=node.task.title,
                                agent_id=node.task.agent_id,
                                error="Verification failed after max attempts",
                            )
                        )
            else:
                error = result.get("error", "Unknown error")
                if ctx.graph.can_retry(task_id):
                    ctx.graph.retry_task(task_id)
                    await queue.put(
                        self._emit(
                            ctx,
                            EngineEventType.TASK_RETRYING,
                            task_id=task_id,
                            title=node.task.title,
                            agent_id=node.task.agent_id,
                            reason=error,
                            next_attempt=node.attempt + 1,
                        )
                    )
                else:
                    ctx.graph.mark_failed(task_id, error)
                    await queue.put(
                        self._emit(
                            ctx,
                            EngineEventType.TASK_FAILED,
                            task_id=task_id,
                            title=node.task.title,
                            agent_id=node.task.agent_id,
                            error=error,
                        )
                    )

        except asyncio.CancelledError:
            # Task was cancelled (e.g., due to pause)
            node.log("Task cancelled")
            raise
        except Exception as e:
            logger.exception(f"Task {task_id} execution error: {e}")
            ctx.graph.mark_failed(task_id, str(e))
            await queue.put(
                self._emit(ctx, EngineEventType.TASK_FAILED, task_id=task_id, error=str(e))
            )

    async def _check_acceptance(
        self,
        ctx: RunContext,
        node: TaskNode,
        criterion: AcceptanceCriterion,
        queue: asyncio.Queue,
    ) -> bool:
        """Check a single acceptance criterion."""
        if criterion.verification_type == "human_approval":
            key = f"{node.task_id}:{criterion.id}"
            
            # Check if already decided
            if key in ctx.approval_decisions:
                return ctx.approval_decisions[key]
                
            # Create event
            event = asyncio.Event()
            ctx.approval_events[key] = event
            
            # Emit request
            await queue.put(
                self._emit(
                    ctx,
                    EngineEventType.APPROVAL_REQUESTED,
                    task_id=node.task_id,
                    criterion_id=criterion.id,
                    description=criterion.description,
                )
            )
            
            # Wait for approval
            await event.wait()
            
            # Return decision
            return ctx.approval_decisions.get(key, False)

        if criterion.verification_type == "agent_review":
            # Autonomous review
            from app.agents.registry import agent_registry
            reviewer = agent_registry.get("reviewer")
            if not reviewer:
                node.log("Reviewer agent not found")
                return False

            # Build review prompt
            review_prompt = f"""Review this implementation:

TASK: {node.task.title}
DESCRIPTION: {node.task.description}

TARGET FILES:
{json.dumps(node.task.target_files, indent=2)}

ARTIFACTS PRODUCED:
{json.dumps([f"{k}: {type(v).__name__}" for k, v in node.artifacts.items()], indent=2)}

OUTPUT:
{node.result.get('response', 'No text response') if isinstance(node.result, dict) else str(node.result)}

Check specifically for: {criterion.description}
"""

            # Run reviewer
            response_text = ""
            try:
                # Emit start event
                await queue.put(
                    self._emit(
                        ctx,
                        EngineEventType.TASK_STARTED,
                        task_id=f"{node.task_id}-review",
                        agent_id="reviewer",
                        title=f"Reviewing {node.task.title}",
                        attempt=1,
                    )
                )

                async for chunk in reviewer.chat(
                    messages=[{"role": "user", "content": review_prompt}],
                    context={"workspace": ctx.workspace_path},
                ):
                    response_text += chunk
                    # Optional: emit progress for review

                # Check decision
                approved = "Review Decision: APPROVED" in response_text or "Review Decision: APPROVED_WITH_SUGGESTIONS" in response_text
                
                # Emit completion
                await queue.put(
                    self._emit(
                        ctx,
                        EngineEventType.TASK_COMPLETED,
                        task_id=f"{node.task_id}-review",
                        result={"success": True, "response": response_text},
                        artifacts={},
                    )
                )
                
                if not approved:
                     node.log(f"Review rejected: {response_text[-100:]}")
                     # Append feedback to the task for next retry if applicable
                     if ctx.graph.can_retry(node.task_id):
                        feedback = f"\n\nREVIEW FEEDBACK (Attempt {node.attempt}):\n{response_text}"
                        node.task.description += feedback 

                return approved

            except Exception as e:
                node.log(f"Review failed: {e}")
                return False

        if criterion.verification_type == "manual":
            return True  # Manual criteria are assumed passed

        if criterion.command:
            try:
                proc = await asyncio.create_subprocess_shell(
                    criterion.command,
                    cwd=ctx.workspace_path,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                _, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
                return proc.returncode == 0
            except Exception as e:
                node.log(f"Acceptance check failed: {e}")
                return False

        return True  # Default to passed if no command

    def _emit(
        self,
        ctx: RunContext,
        event_type: EngineEventType,
        **data,
    ) -> EngineEvent:
        """Create and return an engine event."""
        return EngineEvent(
            type=event_type,
            run_id=ctx.run_id,
            data=data,
        )

    def _fail(
        self,
        ctx: RunContext,
        error: str,
    ) -> Iterator[EngineEvent]:
        """Transition to failed state and emit error event."""
        ctx.error = error
        ctx.transition_to(RunState.FAILED)
        yield self._emit(ctx, EngineEventType.RUN_ERROR, error=error)
        yield self._emit(ctx, EngineEventType.RUN_STATE, state="failed", error=error)

    # =========================================================================
    # Control Methods
    # =========================================================================

    async def submit_approval(self, run_id: str, task_id: str, criterion_id: str, approved: bool) -> bool:
        """Submit a human approval decision."""
        ctx = self._active_runs.get(run_id)
        if not ctx:
            return False
            
        key = f"{task_id}:{criterion_id}"
        if key in ctx.approval_events:
            ctx.approval_decisions[key] = approved
            ctx.approval_events[key].set()
            # Also emit event confirming receipt
            # This will be picked up by the streaming loop if running
            # If not running (e.g. paused), we might miss it in stream unless we handle it differently.
            # But the task is waiting on event, so it will wake up.
            return True
        return False

    async def pause(self, run_id: str) -> bool:
        """Pause a running orchestration."""
        ctx = self._active_runs.get(run_id)
        if not ctx:
            return False

        if ctx.state in (RunState.PLAN, RunState.EXECUTE):
            ctx.resume_state = ctx.state
            ctx.paused_at = datetime.utcnow()
            ctx.transition_to(RunState.PAUSED)
            return True
        return False

    async def resume(self, run_id: str) -> AsyncIterator[EngineEvent]:
        """Resume a paused orchestration.

        Yields events if resuming, yields nothing if cannot resume.
        """
        ctx = self._active_runs.get(run_id)
        if not ctx or ctx.state != RunState.PAUSED:
            return  # Yields nothing if cannot resume

        if ctx.resume_state:
            ctx.state = ctx.resume_state
            ctx.resume_state = None
            ctx.paused_at = None

            yield self._emit(ctx, EngineEventType.RESUMED)

            async for event in self._run_state_machine(ctx):
                yield event

    async def cancel(self, run_id: str) -> bool:
        """Cancel an orchestration run."""
        ctx = self._active_runs.get(run_id)
        if not ctx:
            return False

        if ctx.state not in (RunState.DONE, RunState.FAILED, RunState.CANCELLED):
            ctx.transition_to(RunState.CANCELLED)
            return True
        return False

    def get_run_state(self, run_id: str) -> dict | None:
        """Get the current state of a run for persistence."""
        ctx = self._active_runs.get(run_id)
        if ctx:
            return ctx.to_dict()
        return None


# =============================================================================
# Protocol Interfaces
# =============================================================================

class PlannerProtocol:
    """Protocol for planner implementations."""

    async def create_plan(self, ctx: RunContext) -> AsyncIterator[EngineEvent]:
        """Create an execution plan from the context."""
        raise NotImplementedError


class ExecutorProtocol:
    """Protocol for task executor implementations."""

    async def execute_task(
        self,
        ctx: RunContext,
        node: TaskNode,
        inputs: dict[str, Any],
        on_progress: Callable[[float], None],
        on_output: Callable[[str], None],
    ) -> dict[str, Any]:
        """Execute a single task and return result."""
        raise NotImplementedError


class VerifierProtocol:
    """Protocol for verification implementations."""

    async def verify(self, ctx: RunContext) -> AsyncIterator[EngineEvent]:
        """Run final verification pass."""
        raise NotImplementedError


# =============================================================================
# Default Implementations
# =============================================================================

class DefaultPlanner(PlannerProtocol):
    """Default planner using architect agent."""

    async def create_plan(self, ctx: RunContext) -> AsyncIterator[EngineEvent]:
        """Create plan using architect agent."""
        from app.agents.registry import agent_registry

        architect = agent_registry.get("architect")
        if not architect:
            raise RuntimeError("Architect agent not available")

        # Define strategies: Try with RFCs first, fallback to simpler prompt if failed
        attempts = []
        
        # Attempt 1: Full Context with RFCs
        rfcs_text = ""
        if ctx.context_data.get("brainstorm_rfcs"):
            rfcs = ctx.context_data["brainstorm_rfcs"]
            rfcs_text = "\n\n## EXPERT BRAINSTORMING (THE COUNCIL)\n"
            rfcs_text += "The Council of Specialists has already brainstormed this approach. Use these architecture decisions as your primary guide:\n\n"
            for rfc in rfcs:
                rfcs_text += f"### {rfc['role'].upper()} RFC\n{rfc['content']}\n\n"
        
        attempts.append({"use_rfcs": True, "rfcs_text": rfcs_text})
        
        # Attempt 2: Fallback without RFCs (if we had them)
        if rfcs_text:
             attempts.append({"use_rfcs": False, "rfcs_text": ""})

        last_error = None

        for i, attempt in enumerate(attempts):
            if i > 0:
                logger.warning(f"Retrying planning without brainstorming context (Attempt {i+1})")
                
            rfcs_content = attempt["rfcs_text"]
            
            # Build planning prompt
            planning_prompt = f"""Analyze this request and create a detailed execution plan.

REQUEST:
{ctx.original_prompt}

WORKSPACE: {ctx.workspace_path or 'Not specified'}{rfcs_content}

You must output a JSON execution plan with this structure:
{{
    "plan_id": "plan-<unique-id>",
    "summary": "Brief summary of the plan",
    "tasks": [
        {{
            "id": "task-001",
            "title": "Task title",
            "description": "Detailed description",
            "agent_id": "coder|tester|reviewer|docs|devops",
            "depends_on": ["task-000"],
            "acceptance": [
                {{"id": "ac-001", "description": "Code passes review", "verification_type": "agent_review"}}
            ],
            "target_files": ["path/to/file.py"]
        }}
    ]
}}

Output ONLY the JSON, no other text.
"""

            try:
                response_text = ""
                async for chunk in architect.chat(
                    messages=[{"role": "user", "content": planning_prompt}],
                    context={"workspace": ctx.workspace_path},
                ):
                    response_text += chunk
                    yield EngineEvent(
                        type=EngineEventType.PLANNING_PROGRESS,
                        run_id=ctx.run_id,
                        data={"progress": min(len(response_text) / 2000, 0.9)},
                    )

                logger.info(f"Planner response length (Attempt {i+1}): {len(response_text)}")
                
                if not response_text.strip():
                    raise ValueError("Empty response from Planner Agent")

                # Parse JSON
                json_str = response_text
                plan_data = None
                
                # Method 1: Markdown blocks (most reliable if present)
                if "```json" in json_str:
                    try:
                        block = json_str.split("```json")[1].split("```")[0].strip()
                        plan_data = json.loads(block)
                    except Exception:
                        pass # Fallback to search
                elif "```" in json_str:
                    try:
                        block = json_str.split("```")[1].split("```")[0].strip()
                        plan_data = json.loads(block)
                    except Exception:
                        pass

                # Method 2: Scan for JSON object using raw_decode
                if not plan_data:
                    decoder = json.JSONDecoder()
                    # Search for start of object
                    idx = 0
                    while idx < len(json_str):
                        next_brace = json_str.find('{', idx)
                        if next_brace == -1:
                            break
                        
                        try:
                            plan_data, end_idx = decoder.raw_decode(json_str[next_brace:])
                            # Verify it looks like a plan (has 'tasks' or 'summary') to avoid capturing trivial objects
                            if isinstance(plan_data, dict) and ("tasks" in plan_data or "summary" in plan_data):
                                break
                            else:
                                # Not the droids we're looking for, keep searching
                                idx = next_brace + 1
                                plan_data = None
                        except ValueError:
                            # Not valid JSON starting here
                            idx = next_brace + 1
                
                if not plan_data:
                    # Final desperate fallback: Regex extraction for messy cases
                    # (This helps if raw_decode failed due to minor syntax error usually caught by stricter parsers, 
                    # but sometimes json.loads is more lenient than raw_decode? No, they are same backend usually.
                    # But maybe we can try to fix it.)
                    import re
                    # Non-greedy search for { ... }
                    json_match = re.search(r"(\{.*\})", json_str, re.DOTALL)
                    if json_match:
                        try:
                            # Try to fix common missing comma issue: " "\n" -> ", "\n"
                            candidate = json_match.group(1)
                            candidate = re.sub(r'\"\s*\n\s*\"', '",\n"', candidate)
                            plan_data = json.loads(candidate)
                        except:
                            pass

                if not plan_data:
                     raise ValueError("Could not extract valid JSON plan from response")

                # Add required fields
                plan_data["original_prompt"] = ctx.original_prompt
                plan_data["workspace_path"] = ctx.workspace_path
                plan_data["version"] = "1.0"
                if "plan_id" not in plan_data:
                    plan_data["plan_id"] = f"plan-{uuid.uuid4().hex[:8]}"

                plan = ExecutionPlan.model_validate(plan_data)

                yield EngineEvent(
                    type=EngineEventType.PLANNING_COMPLETED,
                    run_id=ctx.run_id,
                    data={"plan": plan},
                )
                return

            except Exception as e:
                logger.warning(f"Planning attempt {i+1} failed: {e}")
                if "JSONDecodeError" in str(type(e)):
                     logger.error(f"Failed JSON content: {response_text[:500]}...")
                last_error = e
                # Continue to next fallback attempt

        logger.exception("All planning attempts failed")
        raise ValueError(f"Failed to parse execution plan after validation: {last_error}")


class DefaultExecutor(ExecutorProtocol):
    """Default task executor using subagent manager."""

    async def execute_task(
        self,
        ctx: RunContext,
        node: TaskNode,
        inputs: dict[str, Any],
        on_progress: Callable[[float], None],
        on_output: Callable[[str], None],
    ) -> dict[str, Any]:
        """Execute task via agent."""
        from app.agents.registry import agent_registry

        agent = agent_registry.get(node.task.agent_id)
        if not agent:
            return {"success": False, "error": f"Agent not found: {node.task.agent_id}"}

        # Build task prompt
        task_prompt = f"""Execute this task:

TITLE: {node.task.title}

DESCRIPTION:
{node.task.description}

TARGET FILES: {', '.join(node.task.target_files) or 'Not specified'}

ACCEPTANCE CRITERIA:
{chr(10).join(f'- {a.description}' for a in node.task.acceptance) or 'None specified'}

INPUTS FROM DEPENDENCIES:
{json.dumps(inputs, indent=2) if inputs else 'None'}
"""

        # Add failure context if this is a retry
        if node.attempt > 1 and node.verification_results:
            failed_criteria = [
                f"- {c.description}" 
                for c in node.task.acceptance 
                if c.id in node.verification_results and not node.verification_results[c.id]
            ]
            if failed_criteria:
                task_prompt += f"""
CRITICAL - PREVIOUS ATTEMPT FAILED:
The previous implementation failed the following verification checks. 
YOU MUST FIX THESE ISSUES IN THIS ATTEMPT.

FAILED CHECKS:
{chr(10).join(failed_criteria)}

Refine your implementation to specifically address these failures.
"""

        response_text = ""
        try:
            async for chunk in agent.chat(
                messages=[{"role": "user", "content": task_prompt}],
                context={"workspace": ctx.workspace_path},
            ):
                response_text += chunk
                on_output(chunk)

                # Update progress based on response length
                progress = min(len(response_text) / 3000, 0.95)
                on_progress(progress)

            on_progress(1.0)
            node.result = response_text

            # Extract any artifacts from response using regex
            # Pattern matches ```lang:path/to/file.ext
            import re
            # Matches ```python:src/main.py or ```:src/main.py
            code_block_pattern = r"```(?:\w+)?[:](.+?)\n"
            found_files = re.findall(code_block_pattern, response_text)
            
            for fpath in found_files:
                clean_path = fpath.strip()
                node.artifacts[clean_path] = "File"
            
            # Also support "Files changed:" listing if code blocks miss some
            # This is a fallback heuristic
            if "Files changed:" in response_text:
                try:
                    section = response_text.split("Files changed:")[1].split("\n\n")[0]
                    for line in section.strip().split("\n"):
                        if line.strip().startswith("- "):
                            path = line.strip()[2:].strip()
                            if path and path not in node.artifacts:
                                node.artifacts[path] = "File"
                except Exception:
                     pass # Fallback parsing failed, ignore

            return {"success": True, "response": response_text}

        except Exception as e:
            logger.exception(f"Task execution failed: {e}")
            return {"success": False, "error": str(e)}


class DefaultVerifier(VerifierProtocol):
    """Default verifier - runs acceptance criteria."""

    async def verify(self, ctx: RunContext) -> AsyncIterator[EngineEvent]:
        """Run final verification."""
        # In the default implementation, per-task verification handles most cases
        # This is for any final cross-cutting verification

        all_passed = True
        failed_tasks = []

        for node in ctx.graph.nodes.values():
            if node.status == TaskNodeStatus.COMPLETED:
                # Check all verification results
                for criterion_id, passed in node.verification_results.items():
                    if not passed:
                        all_passed = False
                        failed_tasks.append(node.task_id)

        yield EngineEvent(
            type=EngineEventType.VERIFICATION_COMPLETED,
            run_id=ctx.run_id,
            data={
                "passed": all_passed,
                "failed_tasks": failed_tasks,
                "retry_tasks": failed_tasks if not all_passed else [],
            },
        )


# =============================================================================
# Singleton Instance
# =============================================================================

# Global engine instance
_engine: OrchestrationEngine | None = None


def get_engine() -> OrchestrationEngine:
    """Get the global orchestration engine instance."""
    global _engine
    if _engine is None:
        _engine = OrchestrationEngine()
    return _engine
