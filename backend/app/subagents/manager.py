"""Subagent manager for spawning and tracking background tasks."""

import asyncio
import traceback
import uuid
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)

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


class SubagentManager:
    """Manages subagent tasks."""

    def __init__(self) -> None:
        self._tasks: dict[str, SubagentTask] = {}
        self._running: dict[str, asyncio.Task] = {}
        self._fallback_tasks: dict[str, str] = {}  # original_task_id -> fallback_task_id

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

        Returns:
            The created SubagentTask
        """
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

        # Start the task in background with retry/timeout handling
        async_task = asyncio.create_task(
            self._run_task_with_recovery(task, work_fn, enable_fallback)
        )
        self._running[task.id] = async_task

        logger.info(f"Spawned subagent task: {task.id} - {name}")
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


# Global subagent manager
subagent_manager = SubagentManager()
