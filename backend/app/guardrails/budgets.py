"""Budget tracking and enforcement for agent execution.

Tracks resource usage against policy limits:
- Tool call counts
- Shell execution time
- Spawned task counts
- Output sizes
"""

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.guardrails.policies import BudgetPolicy

logger = logging.getLogger(__name__)


class BudgetType(str, Enum):
    """Types of budget limits."""

    TOOL_LOOPS = "tool_loops"
    TOOL_CALLS_MESSAGE = "tool_calls_message"
    TOOL_CALLS_SESSION = "tool_calls_session"
    SPAWNED_TASKS = "spawned_tasks"
    SPAWN_DEPTH = "spawn_depth"
    SHELL_TIME = "shell_time"
    SHELL_CALLS = "shell_calls"
    TOTAL_SHELL_TIME = "total_shell_time"
    OUTPUT_SIZE = "output_size"


class BudgetExceededError(Exception):
    """Raised when a budget limit is exceeded."""

    def __init__(
        self,
        budget_type: BudgetType,
        current: float | int,
        limit: float | int,
        message: str | None = None,
    ):
        self.budget_type = budget_type
        self.current = current
        self.limit = limit
        self.message = message or f"Budget exceeded: {budget_type.value} ({current} > {limit})"
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        return {
            "budget_type": self.budget_type.value,
            "current": self.current,
            "limit": self.limit,
            "message": self.message,
        }


@dataclass
class BudgetUsage:
    """Tracks resource usage during an execution session."""

    # Counters
    tool_loops: int = 0
    tool_calls_message: int = 0
    tool_calls_session: int = 0
    spawned_tasks: int = 0
    spawn_depth: int = 0
    shell_calls: int = 0

    # Accumulators
    total_shell_time_seconds: float = 0.0
    total_output_bytes: int = 0

    # Per-call tracking
    current_shell_start: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_loops": self.tool_loops,
            "tool_calls_message": self.tool_calls_message,
            "tool_calls_session": self.tool_calls_session,
            "spawned_tasks": self.spawned_tasks,
            "spawn_depth": self.spawn_depth,
            "shell_calls": self.shell_calls,
            "total_shell_time_seconds": round(self.total_shell_time_seconds, 2),
            "total_output_bytes": self.total_output_bytes,
        }


class BudgetTracker:
    """Tracks and enforces budget limits during agent execution.

    Usage:
        tracker = BudgetTracker(policy)

        # Check before action
        tracker.check_tool_call()

        # Record after action
        tracker.record_tool_call()

        # For shell commands with timing
        with tracker.shell_execution():
            result = await run_shell_command(...)
    """

    def __init__(
        self,
        policy: BudgetPolicy,
        session_id: str | None = None,
        agent_id: str | None = None,
    ):
        self.policy = policy
        self.session_id = session_id
        self.agent_id = agent_id
        self.usage = BudgetUsage()
        self._message_start_time = time.time()

    def reset_message_counters(self) -> None:
        """Reset per-message counters (call at start of new message)."""
        self.usage.tool_loops = 0
        self.usage.tool_calls_message = 0
        self.usage.shell_calls = 0
        self._message_start_time = time.time()

    # =========================================================================
    # Check methods (raise if would exceed)
    # =========================================================================

    def check_tool_loop(self) -> None:
        """Check if another tool loop iteration is allowed."""
        if self.usage.tool_loops >= self.policy.max_tool_loops_per_message:
            raise BudgetExceededError(
                BudgetType.TOOL_LOOPS,
                self.usage.tool_loops,
                self.policy.max_tool_loops_per_message,
                f"Maximum tool loop iterations ({self.policy.max_tool_loops_per_message}) exceeded",
            )

    def check_tool_call(self) -> None:
        """Check if another tool call is allowed."""
        if self.usage.tool_calls_message >= self.policy.max_tool_calls_per_message:
            raise BudgetExceededError(
                BudgetType.TOOL_CALLS_MESSAGE,
                self.usage.tool_calls_message,
                self.policy.max_tool_calls_per_message,
                f"Maximum tool calls per message ({self.policy.max_tool_calls_per_message}) exceeded",
            )

        if self.usage.tool_calls_session >= self.policy.max_tool_calls_per_session:
            raise BudgetExceededError(
                BudgetType.TOOL_CALLS_SESSION,
                self.usage.tool_calls_session,
                self.policy.max_tool_calls_per_session,
                f"Maximum tool calls per session ({self.policy.max_tool_calls_per_session}) exceeded",
            )

    def check_spawn(self, depth: int = 0) -> None:
        """Check if spawning another task is allowed."""
        if self.usage.spawned_tasks >= self.policy.max_spawned_tasks_per_run:
            raise BudgetExceededError(
                BudgetType.SPAWNED_TASKS,
                self.usage.spawned_tasks,
                self.policy.max_spawned_tasks_per_run,
                f"Maximum spawned tasks ({self.policy.max_spawned_tasks_per_run}) exceeded",
            )

        if depth >= self.policy.max_nested_spawn_depth:
            raise BudgetExceededError(
                BudgetType.SPAWN_DEPTH,
                depth,
                self.policy.max_nested_spawn_depth,
                f"Maximum spawn nesting depth ({self.policy.max_nested_spawn_depth}) exceeded",
            )

    def check_shell_call(self) -> None:
        """Check if another shell call is allowed."""
        if self.usage.shell_calls >= self.policy.max_shell_calls_per_message:
            raise BudgetExceededError(
                BudgetType.SHELL_CALLS,
                self.usage.shell_calls,
                self.policy.max_shell_calls_per_message,
                f"Maximum shell calls per message ({self.policy.max_shell_calls_per_message}) exceeded",
            )

        if self.usage.total_shell_time_seconds >= self.policy.max_total_shell_time_per_session:
            raise BudgetExceededError(
                BudgetType.TOTAL_SHELL_TIME,
                self.usage.total_shell_time_seconds,
                self.policy.max_total_shell_time_per_session,
                f"Maximum total shell time ({self.policy.max_total_shell_time_per_session}s) exceeded",
            )

    def check_output_size(self, size_bytes: int) -> None:
        """Check if output size is within limits."""
        if size_bytes > self.policy.max_output_size_bytes:
            raise BudgetExceededError(
                BudgetType.OUTPUT_SIZE,
                size_bytes,
                self.policy.max_output_size_bytes,
                f"Output size ({size_bytes} bytes) exceeds limit ({self.policy.max_output_size_bytes})",
            )

    # =========================================================================
    # Record methods
    # =========================================================================

    def record_tool_loop(self) -> None:
        """Record a tool loop iteration."""
        self.usage.tool_loops += 1
        logger.debug(
            f"Tool loop {self.usage.tool_loops}/{self.policy.max_tool_loops_per_message}"
        )

    def record_tool_call(self, output_size: int = 0) -> None:
        """Record a tool call."""
        self.usage.tool_calls_message += 1
        self.usage.tool_calls_session += 1
        self.usage.total_output_bytes += output_size

    def record_spawn(self, depth: int = 0) -> None:
        """Record a task spawn."""
        self.usage.spawned_tasks += 1
        self.usage.spawn_depth = max(self.usage.spawn_depth, depth)

    def record_shell_time(self, duration_seconds: float) -> None:
        """Record shell execution time."""
        self.usage.shell_calls += 1
        self.usage.total_shell_time_seconds += duration_seconds

    # =========================================================================
    # Context managers
    # =========================================================================

    class ShellExecutionContext:
        """Context manager for tracking shell execution time."""

        def __init__(self, tracker: "BudgetTracker"):
            self.tracker = tracker
            self.start_time: float = 0

        def __enter__(self) -> "BudgetTracker.ShellExecutionContext":
            self.tracker.check_shell_call()
            self.start_time = time.time()
            return self

        def __exit__(self, exc_type, exc_val, exc_tb) -> None:
            duration = time.time() - self.start_time
            self.tracker.record_shell_time(duration)

            # Check if we exceeded the per-call limit
            if duration > self.tracker.policy.max_shell_time_seconds:
                logger.warning(
                    f"Shell execution exceeded time limit: "
                    f"{duration:.2f}s > {self.tracker.policy.max_shell_time_seconds}s"
                )

    def shell_execution(self) -> ShellExecutionContext:
        """Context manager for shell execution timing."""
        return self.ShellExecutionContext(self)

    # =========================================================================
    # Utility methods
    # =========================================================================

    def get_remaining(self) -> dict[str, Any]:
        """Get remaining budget for each limit type."""
        return {
            "tool_loops": self.policy.max_tool_loops_per_message - self.usage.tool_loops,
            "tool_calls_message": self.policy.max_tool_calls_per_message - self.usage.tool_calls_message,
            "tool_calls_session": self.policy.max_tool_calls_per_session - self.usage.tool_calls_session,
            "spawned_tasks": self.policy.max_spawned_tasks_per_run - self.usage.spawned_tasks,
            "shell_calls": self.policy.max_shell_calls_per_message - self.usage.shell_calls,
            "shell_time": self.policy.max_total_shell_time_per_session - self.usage.total_shell_time_seconds,
        }

    def get_usage_summary(self) -> dict[str, Any]:
        """Get summary of budget usage."""
        return {
            "usage": self.usage.to_dict(),
            "remaining": self.get_remaining(),
            "policy": {
                "max_tool_loops": self.policy.max_tool_loops_per_message,
                "max_tool_calls_message": self.policy.max_tool_calls_per_message,
                "max_tool_calls_session": self.policy.max_tool_calls_per_session,
                "max_spawned_tasks": self.policy.max_spawned_tasks_per_run,
                "max_shell_time": self.policy.max_shell_time_seconds,
            },
        }

    def is_budget_exhausted(self) -> bool:
        """Check if any budget is exhausted."""
        remaining = self.get_remaining()
        return any(v <= 0 for v in remaining.values() if isinstance(v, (int, float)))
