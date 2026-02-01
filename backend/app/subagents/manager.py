"""Subagent manager for spawning and tracking background tasks.

Enterprise guardrails integration:
- Budget enforcement for spawned tasks
- Audit logging for task lifecycle
- Per-agent spawn limits
"""

import asyncio
import traceback
import uuid
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)

# Guardrails integration (optional, graceful fallback)
_guardrails_available = False
try:
    from app.guardrails import (
        BudgetTracker,
        BudgetExceededError,
        AuditRepository,
        get_agent_policy,
    )
    _guardrails_available = True
except ImportError:
    logger.info("Guardrails module not available, using basic mode")

# Lazy imports to avoid circular imports
_metrics_manager = None
_failure_logger = None
_default_recovery_config = None


def get_metrics_manager():
    """Get or create the metrics manager."""
    global _metrics_manager
    if _metrics_manager is None:
        from app.subagents.metrics import task_metrics
        _metrics_manager = task_metrics
    return _metrics_manager


def get_failure_logger():
    """Get the failure logger."""
    global _failure_logger
    if _failure_logger is None:
        from app.subagents.recovery import failure_logger
        _failure_logger = failure_logger
    return _failure_logger


def get_recovery_config():
    """Get the default recovery config."""
    global _default_recovery_config
    if _default_recovery_config is None:
        from app.subagents.recovery import default_recovery_config
        _default_recovery_config = default_recovery_config
    return _default_recovery_config


class TaskStatus(str, Enum):
    """Subagent task status."""
    PENDING = "pending"
    SPAWNING = "spawning"
    RUNNING = "running"
    RETRYING = "retrying"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


class GoalStatus(str, Enum):
    """Sub-goal status within a task."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class TaskGoal:
    """A sub-goal within a task for finer-grained progress tracking."""
    id: int
    description: str
    status: GoalStatus = GoalStatus.PENDING
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "description": self.description,
            "status": self.status.value,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error": self.error,
        }


@dataclass
class TaskCheckpoint:
    """A checkpoint for task recovery on failure."""
    name: str
    description: str
    created_at: datetime = field(default_factory=datetime.now)
    goal_id: int | None = None  # Associated goal
    context: dict[str, Any] = field(default_factory=dict)  # State to restore

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "created_at": self.created_at.isoformat(),
            "goal_id": self.goal_id,
        }


@dataclass
class SubagentTask:
    """A background task run by a subagent."""

    id: str
    name: str
    description: str
    agent_id: str

    status: TaskStatus = TaskStatus.PENDING
    progress: float = 0.0  # 0-1

    # Timing
    created_at: datetime = field(default_factory=datetime.now)
    started_at: datetime | None = None
    completed_at: datetime | None = None

    # Results
    result: Any = None
    error: str | None = None
    logs: list[str] = field(default_factory=list)

    # Sub-goals for finer-grained tracking
    goals: list[TaskGoal] = field(default_factory=list)
    current_goal_id: int | None = None

    # Checkpoints for recovery
    checkpoints: list[TaskCheckpoint] = field(default_factory=list)

    # Parent task for nested subagents
    parent_id: str | None = None

    # Callback when complete
    callback_session: str | None = None  # Session to notify

    # Retry tracking
    attempt: int = 1
    max_attempts: int = 3
    retry_delay: float = 0.0
    timeout_seconds: float = 300.0  # 5 minutes default

    # Fallback tracking
    fallback_agent_id: str | None = None  # If this task is a fallback
    original_task_id: str | None = None  # The task this is a fallback for

    # Response tracking for recovery
    response_so_far: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "agent_id": self.agent_id,
            "status": self.status.value,
            "progress": self.progress,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "result": self.result,
            "error": self.error,
            "logs": self.logs[-20:],  # Last 20 logs
            "goals": [g.to_dict() for g in self.goals],
            "current_goal_id": self.current_goal_id,
            "checkpoints": [c.to_dict() for c in self.checkpoints],
            "goals_completed": sum(1 for g in self.goals if g.status == GoalStatus.COMPLETED),
            "goals_total": len(self.goals),
            "attempt": self.attempt,
            "max_attempts": self.max_attempts,
            "is_fallback": self.fallback_agent_id is not None,
            "original_task_id": self.original_task_id,
        }

    def log(self, message: str) -> None:
        """Add a log entry."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.logs.append(f"[{timestamp}] {message}")
        logger.info(f"[{self.id}] {message}")

    def add_goal(self, goal_id: int, description: str) -> TaskGoal:
        """Add a sub-goal to this task."""
        goal = TaskGoal(id=goal_id, description=description)
        self.goals.append(goal)
        self.log(f"Goal {goal_id}: {description}")
        return goal

    def start_goal(self, goal_id: int) -> None:
        """Mark a goal as in progress."""
        for goal in self.goals:
            if goal.id == goal_id:
                goal.status = GoalStatus.IN_PROGRESS
                goal.started_at = datetime.now()
                self.current_goal_id = goal_id
                self.log(f"Starting goal {goal_id}")
                break

    def complete_goal(self, goal_id: int) -> None:
        """Mark a goal as completed."""
        for goal in self.goals:
            if goal.id == goal_id:
                goal.status = GoalStatus.COMPLETED
                goal.completed_at = datetime.now()
                self.log(f"Completed goal {goal_id}")
                # Update progress based on goals
                if self.goals:
                    completed = sum(1 for g in self.goals if g.status == GoalStatus.COMPLETED)
                    self.progress = min(0.95, 0.1 + (completed / len(self.goals)) * 0.85)
                break

    def fail_goal(self, goal_id: int, error: str) -> None:
        """Mark a goal as failed."""
        for goal in self.goals:
            if goal.id == goal_id:
                goal.status = GoalStatus.FAILED
                goal.error = error
                self.log(f"Goal {goal_id} failed: {error}")
                break

    def add_checkpoint(self, name: str, description: str, context: dict | None = None) -> TaskCheckpoint:
        """Add a checkpoint for recovery."""
        checkpoint = TaskCheckpoint(
            name=name,
            description=description,
            goal_id=self.current_goal_id,
            context=context or {},
        )
        self.checkpoints.append(checkpoint)
        self.log(f"Checkpoint: {name}")
        return checkpoint

    def get_last_checkpoint(self) -> TaskCheckpoint | None:
        """Get the most recent checkpoint."""
        return self.checkpoints[-1] if self.checkpoints else None


class AgentRateLimiter:
    """Rate limiter for concurrent agent tasks."""

    def __init__(
        self,
        max_total_concurrent: int = 10,
        max_per_agent: int = 3,
    ) -> None:
        self.max_total_concurrent = max_total_concurrent
        self.max_per_agent = max_per_agent
        self._running_by_agent: dict[str, int] = {}
        self._queue: list[tuple[str, asyncio.Event]] = []  # (agent_id, ready_event)
        self._total_running = 0
        self._lock = asyncio.Lock()

    async def acquire(self, agent_id: str) -> bool:
        """Try to acquire a slot for an agent. Returns True if acquired, False if queued."""
        async with self._lock:
            current_for_agent = self._running_by_agent.get(agent_id, 0)

            if self._total_running < self.max_total_concurrent and current_for_agent < self.max_per_agent:
                # Can run immediately
                self._running_by_agent[agent_id] = current_for_agent + 1
                self._total_running += 1
                return True

            # Need to queue
            return False

    async def wait_for_slot(self, agent_id: str) -> None:
        """Wait until a slot is available."""
        ready_event = asyncio.Event()
        self._queue.append((agent_id, ready_event))
        logger.info(f"Agent {agent_id} queued. Queue size: {len(self._queue)}")

        # Wait for the event to be set
        await ready_event.wait()

        # Acquire the slot
        async with self._lock:
            self._running_by_agent[agent_id] = self._running_by_agent.get(agent_id, 0) + 1
            self._total_running += 1

    async def release(self, agent_id: str) -> None:
        """Release a slot when task completes."""
        async with self._lock:
            current = self._running_by_agent.get(agent_id, 0)
            if current > 0:
                self._running_by_agent[agent_id] = current - 1
                self._total_running -= 1

            # Check queue and wake up next waiting task
            if self._queue:
                # Find a task that can run
                for i, (queued_agent, event) in enumerate(self._queue):
                    queued_current = self._running_by_agent.get(queued_agent, 0)
                    if self._total_running < self.max_total_concurrent and queued_current < self.max_per_agent:
                        self._queue.pop(i)
                        event.set()
                        logger.info(f"Agent {queued_agent} released from queue. Remaining: {len(self._queue)}")
                        break

    def get_status(self) -> dict[str, Any]:
        """Get current rate limiter status."""
        return {
            "total_running": self._total_running,
            "max_total_concurrent": self.max_total_concurrent,
            "running_by_agent": dict(self._running_by_agent),
            "max_per_agent": self.max_per_agent,
            "queue_size": len(self._queue),
            "queued_agents": [agent_id for agent_id, _ in self._queue],
        }


class SubagentManager:
    """Manages subagent tasks with database persistence.

    Enterprise guardrails:
    - Enforces spawn limits per session/run via BudgetTracker
    - Logs task lifecycle events to AuditRepository
    - Respects agent-specific policies
    """

    def __init__(
        self,
        max_total_concurrent: int = 10,
        max_per_agent: int = 3,
    ) -> None:
        self._tasks: dict[str, SubagentTask] = {}
        self._running: dict[str, asyncio.Task] = {}
        self._fallback_tasks: dict[str, str] = {}  # original_task_id -> fallback_task_id
        self._rate_limiter = AgentRateLimiter(max_total_concurrent, max_per_agent)
        self._persist_enabled = True  # Can be disabled for testing

        # Budget tracking per session (for spawn limits)
        self._budget_trackers: dict[str, "BudgetTracker"] = {}
        self._spawn_depth: dict[str, int] = {}  # task_id -> depth
        self._enable_guardrails = _guardrails_available

    def get_budget_tracker(self, session_id: str, agent_id: str) -> "BudgetTracker | None":
        """Get or create a budget tracker for a session."""
        if not self._enable_guardrails:
            return None

        key = f"{session_id}:{agent_id}"
        if key not in self._budget_trackers:
            policy = get_agent_policy(agent_id)
            self._budget_trackers[key] = BudgetTracker(
                policy=policy.budget,
                session_id=session_id,
                agent_id=agent_id,
            )
        return self._budget_trackers[key]

    def _get_spawn_depth(self, parent_id: str | None) -> int:
        """Get the spawn depth for a task."""
        if parent_id is None:
            return 0
        return self._spawn_depth.get(parent_id, 0) + 1

    async def _persist_task(self, task: SubagentTask) -> None:
        """Persist task state to database."""
        if not self._persist_enabled:
            return

        try:
            from app.database import SubagentTaskRecord, async_session_factory
            from sqlalchemy import select

            async with async_session_factory() as db:
                # Check if exists
                result = await db.execute(
                    select(SubagentTaskRecord).where(SubagentTaskRecord.id == task.id)
                )
                record = result.scalar_one_or_none()

                if record:
                    # Update existing
                    record.status = task.status.value
                    record.progress = task.progress
                    record.started_at = task.started_at
                    record.completed_at = task.completed_at
                    record.result = task.result
                    record.error = task.error
                    record.logs = task.logs[-50:]  # Keep last 50 logs
                    record.goals = [g.to_dict() for g in task.goals]
                    record.checkpoints = [c.to_dict() for c in task.checkpoints]
                    record.response_so_far = task.response_so_far[:10000] if task.response_so_far else None
                    record.attempt = task.attempt
                else:
                    # Create new
                    record = SubagentTaskRecord(
                        id=task.id,
                        name=task.name,
                        description=task.description,
                        agent_id=task.agent_id,
                        status=task.status.value,
                        progress=task.progress,
                        callback_session=task.callback_session,
                        parent_id=task.parent_id,
                        created_at=task.created_at,
                        started_at=task.started_at,
                        completed_at=task.completed_at,
                        result=task.result,
                        error=task.error,
                        logs=task.logs[-50:],
                        goals=[g.to_dict() for g in task.goals],
                        checkpoints=[c.to_dict() for c in task.checkpoints],
                        response_so_far=task.response_so_far[:10000] if task.response_so_far else None,
                        attempt=task.attempt,
                        max_attempts=task.max_attempts,
                        fallback_agent_id=task.fallback_agent_id,
                        original_task_id=task.original_task_id,
                    )
                    db.add(record)

                await db.commit()
        except Exception as e:
            logger.warning(f"Failed to persist task {task.id}: {e}")

    async def load_interrupted_tasks(self) -> list[SubagentTask]:
        """Load tasks that were running when the server stopped.

        Returns tasks in RUNNING, PENDING, or RETRYING status that can be recovered.
        """
        try:
            from app.database import SubagentTaskRecord, async_session_factory
            from sqlalchemy import select

            interrupted = []
            async with async_session_factory() as db:
                result = await db.execute(
                    select(SubagentTaskRecord).where(
                        SubagentTaskRecord.status.in_(["running", "pending", "retrying", "spawning"])
                    )
                )
                records = result.scalars().all()

                for record in records:
                    # Convert to SubagentTask
                    task = SubagentTask(
                        id=record.id,
                        name=record.name,
                        description=record.description,
                        agent_id=record.agent_id,
                        status=TaskStatus(record.status),
                        progress=record.progress,
                        created_at=record.created_at,
                        started_at=record.started_at,
                        completed_at=record.completed_at,
                        result=record.result,
                        error=record.error,
                        logs=record.logs or [],
                        callback_session=record.callback_session,
                        parent_id=record.parent_id,
                        attempt=record.attempt,
                        max_attempts=record.max_attempts,
                        fallback_agent_id=record.fallback_agent_id,
                        original_task_id=record.original_task_id,
                        response_so_far=record.response_so_far or "",
                    )

                    # Restore goals
                    if record.goals:
                        for g in record.goals:
                            task.goals.append(TaskGoal(
                                id=g["id"],
                                description=g["description"],
                                status=GoalStatus(g["status"]),
                                started_at=datetime.fromisoformat(g["started_at"]) if g.get("started_at") else None,
                                completed_at=datetime.fromisoformat(g["completed_at"]) if g.get("completed_at") else None,
                                error=g.get("error"),
                            ))

                    # Restore checkpoints
                    if record.checkpoints:
                        for c in record.checkpoints:
                            task.checkpoints.append(TaskCheckpoint(
                                name=c["name"],
                                description=c["description"],
                                created_at=datetime.fromisoformat(c["created_at"]) if c.get("created_at") else datetime.now(),
                                goal_id=c.get("goal_id"),
                            ))

                    interrupted.append(task)
                    self._tasks[task.id] = task

                    # Mark as needing recovery
                    task.log("Task restored after server restart - needs recovery")

            logger.info(f"Loaded {len(interrupted)} interrupted tasks from database")
            return interrupted

        except Exception as e:
            logger.error(f"Failed to load interrupted tasks: {e}", exc_info=True)
            return []

    async def mark_interrupted_as_failed(self) -> int:
        """Mark all interrupted tasks as failed (for cases where recovery isn't possible).

        Returns the number of tasks marked as failed.
        """
        try:
            from app.database import SubagentTaskRecord, async_session_factory
            from sqlalchemy import update

            async with async_session_factory() as db:
                result = await db.execute(
                    update(SubagentTaskRecord)
                    .where(SubagentTaskRecord.status.in_(["running", "pending", "retrying", "spawning"]))
                    .values(
                        status="failed",
                        error="Server restart - task interrupted",
                        completed_at=datetime.now(),
                    )
                )
                await db.commit()
                return result.rowcount

        except Exception as e:
            logger.error(f"Failed to mark interrupted tasks: {e}", exc_info=True)
            return 0

    async def spawn(
        self,
        name: str,
        description: str,
        agent_id: str,
        work_fn: Callable[["SubagentTask"], Coroutine[Any, Any, Any]],
        parent_id: str | None = None,
        callback_session: str | None = None,
        max_attempts: int = 3,
        timeout_seconds: float = 300.0,
        enable_fallback: bool = True,
        session_id: str | None = None,  # For budget tracking
        budget_agent_id: str | None = None,  # Which agent's budget to check (default: "mo")
    ) -> SubagentTask:
        """Spawn a new subagent task with error recovery.

        Args:
            name: Task name
            description: What the task does
            agent_id: Which agent runs this
            work_fn: Async function that does the work (receives task for logging/progress)
            parent_id: Parent task ID if nested
            callback_session: Session to notify when complete
            max_attempts: Maximum retry attempts (default 3)
            timeout_seconds: Timeout per attempt in seconds (default 300)
            enable_fallback: Whether to try fallback agents on failure (default True)
            session_id: Session ID for budget tracking (optional)
            budget_agent_id: Which agent's budget policy to use for spawn limits (default: "mo")

        Returns:
            The created SubagentTask

        Raises:
            BudgetExceededError: If spawn limits are exceeded
        """
        # Calculate spawn depth
        spawn_depth = self._get_spawn_depth(parent_id)

        # Check budget limits if guardrails enabled
        # Use budget_agent_id (default: "mo") since MO is the orchestrator that spawns agents
        session_for_budget = session_id or callback_session
        budget_agent = budget_agent_id or "mo"
        if self._enable_guardrails and session_for_budget:
            budget_tracker = self.get_budget_tracker(session_for_budget, budget_agent)
            if budget_tracker:
                try:
                    budget_tracker.check_spawn(depth=spawn_depth)
                except BudgetExceededError as e:
                    # Log the budget violation
                    try:
                        await AuditRepository.log_budget_check(
                            budget_type=e.budget_type.value,
                            current_value=float(e.current),
                            limit_value=float(e.limit),
                            exceeded=True,
                            session_id=session_for_budget,
                            agent_id=agent_id,
                        )
                        await AuditRepository.log_event(
                            category="subagent",
                            action="spawn_blocked",
                            session_id=session_for_budget,
                            agent_id=agent_id,
                            success=False,
                            error=e.message,
                            severity="warning",
                            metadata={
                                "task_name": name,
                                "spawn_depth": spawn_depth,
                                "budget_type": e.budget_type.value,
                            },
                        )
                    except Exception as log_err:
                        logger.error(f"Failed to log budget violation: {log_err}")
                    raise  # Re-raise the BudgetExceededError

        task = SubagentTask(
            id=str(uuid.uuid4())[:8],
            name=name,
            description=description,
            agent_id=agent_id,
            parent_id=parent_id,
            callback_session=callback_session,
            max_attempts=max_attempts,
            timeout_seconds=timeout_seconds,
        )

        self._tasks[task.id] = task
        self._spawn_depth[task.id] = spawn_depth

        # Record spawn in budget tracker (use budget_agent for consistency)
        if self._enable_guardrails and session_for_budget:
            budget_tracker = self.get_budget_tracker(session_for_budget, budget_agent)
            if budget_tracker:
                budget_tracker.record_spawn(depth=spawn_depth)

        # Log task spawn to audit
        if self._enable_guardrails:
            try:
                await AuditRepository.log_event(
                    category="subagent",
                    action="spawn",
                    session_id=session_for_budget,
                    task_id=task.id,
                    agent_id=agent_id,
                    success=True,
                    metadata={
                        "task_name": name,
                        "description": description[:200],
                        "parent_id": parent_id,
                        "spawn_depth": spawn_depth,
                    },
                )
            except Exception as log_err:
                logger.warning(f"Failed to log task spawn: {log_err}")

        # Check rate limit before starting
        can_run = await self._rate_limiter.acquire(agent_id)
        if not can_run:
            task.status = TaskStatus.PENDING
            task.log("Queued - waiting for available slot")

        # Persist initial task state
        await self._persist_task(task)

        # Start the task in background with retry/timeout handling
        async_task = asyncio.create_task(
            self._run_task_with_rate_limit(task, work_fn, enable_fallback, not can_run)
        )
        self._running[task.id] = async_task

        logger.info(f"Spawned subagent task: {task.id} - {name} (queued={not can_run}, depth={spawn_depth})")
        return task

    async def spawn_fallback(
        self,
        original_task: SubagentTask,
        fallback_agent_id: str,
        modified_prompt: str,
        work_fn: Callable[["SubagentTask"], Coroutine[Any, Any, Any]],
    ) -> SubagentTask:
        """Spawn a fallback task after the original failed.

        Args:
            original_task: The task that failed
            fallback_agent_id: Agent to use for fallback
            modified_prompt: Modified task description for fallback
            work_fn: Work function for the fallback task

        Returns:
            The fallback SubagentTask
        """
        fallback_task = SubagentTask(
            id=str(uuid.uuid4())[:8],
            name=f"Fallback: {original_task.name}",
            description=modified_prompt,
            agent_id=fallback_agent_id,
            parent_id=original_task.parent_id,
            callback_session=original_task.callback_session,
            max_attempts=2,  # Fewer retries for fallback
            timeout_seconds=original_task.timeout_seconds,
            fallback_agent_id=fallback_agent_id,
            original_task_id=original_task.id,
        )

        self._tasks[fallback_task.id] = fallback_task
        self._fallback_tasks[original_task.id] = fallback_task.id

        original_task.log(f"Spawning fallback task {fallback_task.id} using {fallback_agent_id}")

        async_task = asyncio.create_task(
            self._run_task_with_recovery(fallback_task, work_fn, enable_fallback=False)
        )
        self._running[fallback_task.id] = async_task

        logger.info(f"Spawned fallback task: {fallback_task.id} for {original_task.id}")
        return fallback_task

    async def _run_task_with_rate_limit(
        self,
        task: SubagentTask,
        work_fn: Callable[[SubagentTask], Coroutine[Any, Any, Any]],
        enable_fallback: bool,
        needs_to_wait: bool,
    ) -> None:
        """Run task with rate limiting - waits for slot if needed."""
        if needs_to_wait:
            await self._rate_limiter.wait_for_slot(task.agent_id)
            task.log("Slot acquired - starting execution")

        try:
            await self._run_task_with_recovery(task, work_fn, enable_fallback)
        finally:
            await self._rate_limiter.release(task.agent_id)

    async def _run_task_with_recovery(
        self,
        task: SubagentTask,
        work_fn: Callable[[SubagentTask], Coroutine[Any, Any, Any]],
        enable_fallback: bool = True,
    ) -> None:
        """Run a task with retry logic, timeout handling, and fallback support."""
        from app.subagents.recovery import (
            FailureContext,
            FailureType,
            RecoveryStrategy,
            classify_error,
            determine_recovery_action,
            FALLBACK_AGENTS,
        )

        task.status = TaskStatus.RUNNING
        task.started_at = datetime.now()
        task.log(f"Started: {task.description[:100]}...")

        last_error: Exception | None = None
        failure_context: FailureContext | None = None

        for attempt in range(1, task.max_attempts + 1):
            task.attempt = attempt
            attempt_started = datetime.now()

            if attempt > 1:
                task.status = TaskStatus.RETRYING
                task.log(f"Retry attempt {attempt}/{task.max_attempts}")

            try:
                # Execute with timeout
                result = await asyncio.wait_for(
                    work_fn(task),
                    timeout=task.timeout_seconds
                )

                task.result = result
                task.status = TaskStatus.COMPLETED
                task.progress = 1.0
                task.log(f"Completed successfully (attempt {attempt})")
                break

            except asyncio.TimeoutError:
                last_error = asyncio.TimeoutError(
                    f"Task timed out after {task.timeout_seconds}s"
                )
                error_msg = str(last_error)
                failure_type = FailureType.TIMEOUT
                task.status = TaskStatus.TIMED_OUT
                task.log(f"Timeout after {task.timeout_seconds}s (attempt {attempt})")

            except asyncio.CancelledError:
                task.status = TaskStatus.CANCELLED
                task.log("Cancelled")
                task.completed_at = datetime.now()
                self._running.pop(task.id, None)
                await self._persist_task(task)
                return

            except Exception as e:
                last_error = e
                error_msg = str(e)
                failure_type, _ = classify_error(error_msg)
                task.log(f"Error (attempt {attempt}): {error_msg}")
                logger.error(f"Task {task.id} attempt {attempt} failed: {e}", exc_info=True)

            # Create failure context
            attempt_ended = datetime.now()
            goals_completed = sum(1 for g in task.goals if g.status == GoalStatus.COMPLETED)
            last_checkpoint = task.checkpoints[-1].name if task.checkpoints else None

            failure_context = FailureContext(
                task_id=task.id,
                agent_id=task.agent_id,
                task_description=task.description,
                failure_type=failure_type,
                error_message=error_msg,
                attempt=attempt,
                max_attempts=task.max_attempts,
                started_at=attempt_started,
                failed_at=attempt_ended,
                duration_seconds=(attempt_ended - attempt_started).total_seconds(),
                last_checkpoint=last_checkpoint,
                goals_completed=goals_completed,
                goals_total=len(task.goals),
                stack_trace=traceback.format_exc() if last_error else None,
                response_so_far=task.response_so_far,
            )

            # Log failure
            try:
                failure_logger = get_failure_logger()
                failure_logger.log_failure(failure_context)
            except Exception as log_err:
                logger.warning(f"Failed to log failure: {log_err}")

            # Determine recovery action
            try:
                recovery_config = get_recovery_config()
                action = determine_recovery_action(failure_context, recovery_config)

                if action.strategy == RecoveryStrategy.RETRY and attempt < task.max_attempts:
                    task.retry_delay = action.delay_seconds
                    task.log(f"Will retry in {action.delay_seconds:.1f}s: {action.reason}")
                    await asyncio.sleep(action.delay_seconds)
                    continue

            except Exception as recovery_err:
                logger.warning(f"Recovery determination failed: {recovery_err}")

        # All retries exhausted - check for fallback
        if task.status != TaskStatus.COMPLETED and enable_fallback and failure_context:
            fallback_agents = FALLBACK_AGENTS.get(task.agent_id, [])

            if fallback_agents:
                fallback_agent = fallback_agents[0]
                task.log(f"All retries exhausted, attempting fallback to {fallback_agent}")

                try:
                    from app.subagents.recovery import _create_fallback_prompt
                    fallback_prompt = _create_fallback_prompt(failure_context, fallback_agent)

                    # Note: The actual fallback execution would need to be handled by the runner
                    # to create a proper work_fn. For now, just log and mark as failed.
                    task.log(f"Fallback available: {fallback_agent} (requires runner support)")
                except Exception as fb_err:
                    logger.warning(f"Fallback setup failed: {fb_err}")

        # Final status update if still not completed
        if task.status not in (TaskStatus.COMPLETED, TaskStatus.CANCELLED):
            task.status = TaskStatus.FAILED
            task.error = str(last_error) if last_error else "Unknown error"

        task.completed_at = datetime.now()
        self._running.pop(task.id, None)

        # Persist final task state
        await self._persist_task(task)

        # Record task metrics
        try:
            metrics = get_metrics_manager()
            goals_completed = sum(1 for g in task.goals if g.status == GoalStatus.COMPLETED)
            metrics.record(
                task_id=task.id,
                agent_id=task.agent_id,
                task_description=task.description,
                started_at=task.started_at or task.created_at,
                completed_at=task.completed_at,
                success=task.status == TaskStatus.COMPLETED,
                goals_total=len(task.goals),
                goals_completed=goals_completed,
                error=task.error,
            )
        except Exception as e:
            logger.warning(f"Failed to record task metrics: {e}")

        # Log final status
        duration = (task.completed_at - task.started_at).total_seconds() if task.started_at else 0
        logger.info(
            f"Task {task.id} finished: status={task.status.value}, "
            f"attempts={task.attempt}, duration={duration:.1f}s"
        )

        # Log task completion to audit
        if self._enable_guardrails:
            try:
                await AuditRepository.log_event(
                    category="subagent",
                    action="complete" if task.status == TaskStatus.COMPLETED else "failed",
                    session_id=task.callback_session,
                    task_id=task.id,
                    agent_id=task.agent_id,
                    success=task.status == TaskStatus.COMPLETED,
                    error=task.error,
                    duration_ms=duration * 1000,
                    severity="info" if task.status == TaskStatus.COMPLETED else "warning",
                    metadata={
                        "task_name": task.name,
                        "attempts": task.attempt,
                        "goals_completed": sum(1 for g in task.goals if g.status == GoalStatus.COMPLETED),
                        "goals_total": len(task.goals),
                        "is_fallback": task.fallback_agent_id is not None,
                    },
                )
            except Exception as log_err:
                logger.warning(f"Failed to log task completion: {log_err}")

        if task.callback_session:
            logger.info(f"Task {task.id} complete, should notify session {task.callback_session}")
    
    def get(self, task_id: str) -> SubagentTask | None:
        """Get a task by ID."""
        return self._tasks.get(task_id)
    
    def list_tasks(
        self,
        status: TaskStatus | None = None,
        agent_id: str | None = None,
        limit: int = 50,
    ) -> list[SubagentTask]:
        """List tasks with optional filters."""
        tasks = list(self._tasks.values())
        
        if status:
            tasks = [t for t in tasks if t.status == status]
        if agent_id:
            tasks = [t for t in tasks if t.agent_id == agent_id]
        
        # Sort by created time, newest first
        tasks.sort(key=lambda t: t.created_at, reverse=True)
        
        return tasks[:limit]
    
    async def cancel(self, task_id: str) -> bool:
        """Cancel a running task."""
        if task_id in self._running:
            self._running[task_id].cancel()
            return True
        return False

    async def cancel_all(self) -> int:
        """Cancel all running tasks. Returns number of tasks cancelled."""
        cancelled = 0
        for task_id in list(self._running.keys()):
            self._running[task_id].cancel()
            cancelled += 1
        return cancelled

    def get_running_count(self) -> int:
        """Get number of currently running tasks."""
        return len(self._running)

    def get_running_tasks(self) -> list[SubagentTask]:
        """Get list of currently running tasks."""
        return [t for t in self._tasks.values() if t.status in (TaskStatus.RUNNING, TaskStatus.SPAWNING, TaskStatus.RETRYING)]

    
    def cleanup_old(self, max_age_hours: int = 24) -> int:
        """Remove old completed tasks."""
        now = datetime.now()
        to_remove = []

        for task_id, task in self._tasks.items():
            if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED, TaskStatus.TIMED_OUT):
                if task.completed_at:
                    age_hours = (now - task.completed_at).total_seconds() / 3600
                    if age_hours > max_age_hours:
                        to_remove.append(task_id)

        for task_id in to_remove:
            del self._tasks[task_id]

        return len(to_remove)

    async def retry_task(
        self,
        task_id: str,
        work_fn: Callable[["SubagentTask"], Coroutine[Any, Any, Any]],
    ) -> SubagentTask | None:
        """Manually retry a failed task.

        Args:
            task_id: ID of the task to retry
            work_fn: Work function to execute

        Returns:
            The retried task, or None if task not found/not retryable
        """
        task = self._tasks.get(task_id)
        if not task:
            logger.warning(f"Task {task_id} not found for retry")
            return None

        if task.status not in (TaskStatus.FAILED, TaskStatus.TIMED_OUT):
            logger.warning(f"Task {task_id} is not in a retryable state: {task.status}")
            return None

        # Reset task state for retry
        task.status = TaskStatus.PENDING
        task.error = None
        task.attempt = 0
        task.progress = 0.0
        task.response_so_far = ""
        task.log(f"Manual retry requested")

        # Restart the task
        async_task = asyncio.create_task(
            self._run_task_with_recovery(task, work_fn, enable_fallback=True)
        )
        self._running[task.id] = async_task

        logger.info(f"Manually retried task: {task.id}")
        return task

    def get_failure_stats(self) -> dict[str, Any]:
        """Get failure statistics from the failure logger."""
        try:
            failure_logger = get_failure_logger()
            return failure_logger.get_failure_stats()
        except Exception as e:
            logger.warning(f"Failed to get failure stats: {e}")
            return {"error": str(e)}

    def get_recent_failures(
        self,
        agent_id: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Get recent failure contexts.

        Args:
            agent_id: Optional filter by agent
            limit: Maximum number of failures to return

        Returns:
            List of failure context dictionaries
        """
        try:
            failure_logger = get_failure_logger()
            failures = failure_logger.get_recent_failures(agent_id=agent_id, limit=limit)
            return [f.to_dict() for f in failures]
        except Exception as e:
            logger.warning(f"Failed to get recent failures: {e}")
            return []

    def get_fallback_task(self, original_task_id: str) -> SubagentTask | None:
        """Get the fallback task for an original task, if any."""
        fallback_id = self._fallback_tasks.get(original_task_id)
        return self._tasks.get(fallback_id) if fallback_id else None

    def get_rate_limit_status(self) -> dict[str, Any]:
        """Get current rate limiter status."""
        return self._rate_limiter.get_status()

    def configure_rate_limits(
        self,
        max_total_concurrent: int | None = None,
        max_per_agent: int | None = None,
    ) -> None:
        """Configure rate limits."""
        if max_total_concurrent is not None:
            self._rate_limiter.max_total_concurrent = max_total_concurrent
        if max_per_agent is not None:
            self._rate_limiter.max_per_agent = max_per_agent
        logger.info(
            f"Rate limits configured: total={self._rate_limiter.max_total_concurrent}, "
            f"per_agent={self._rate_limiter.max_per_agent}"
        )


# Global subagent manager
subagent_manager = SubagentManager()
