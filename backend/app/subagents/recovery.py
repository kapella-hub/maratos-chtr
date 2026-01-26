"""Error recovery strategies for subagent failures."""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)


class FailureType(str, Enum):
    """Types of agent failures."""
    TIMEOUT = "timeout"
    AGENT_ERROR = "agent_error"
    MEMORY_ERROR = "memory_error"
    TOOL_ERROR = "tool_error"
    API_ERROR = "api_error"
    UNKNOWN = "unknown"


class RecoveryStrategy(str, Enum):
    """Recovery strategies for failed tasks."""
    RETRY = "retry"
    FALLBACK_AGENT = "fallback_agent"
    DIAGNOSE = "diagnose"
    ESCALATE = "escalate"
    ABORT = "abort"


@dataclass
class FailureContext:
    """Context about a task failure for debugging and recovery."""
    task_id: str
    agent_id: str
    task_description: str
    failure_type: FailureType
    error_message: str
    attempt: int
    max_attempts: int
    started_at: datetime
    failed_at: datetime
    duration_seconds: float
    last_checkpoint: str | None = None
    goals_completed: int = 0
    goals_total: int = 0
    stack_trace: str | None = None
    response_so_far: str | None = None
    context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "agent_id": self.agent_id,
            "task_description": self.task_description[:200],
            "failure_type": self.failure_type.value,
            "error_message": self.error_message,
            "attempt": self.attempt,
            "max_attempts": self.max_attempts,
            "started_at": self.started_at.isoformat(),
            "failed_at": self.failed_at.isoformat(),
            "duration_seconds": round(self.duration_seconds, 2),
            "last_checkpoint": self.last_checkpoint,
            "goals_completed": self.goals_completed,
            "goals_total": self.goals_total,
            "has_stack_trace": bool(self.stack_trace),
            "response_length": len(self.response_so_far) if self.response_so_far else 0,
        }


@dataclass
class RecoveryAction:
    """An action to take for recovery."""
    strategy: RecoveryStrategy
    agent_id: str | None = None  # For fallback_agent strategy
    modified_prompt: str | None = None  # Modified task description
    delay_seconds: float = 0.0  # Delay before retry
    diagnostic_prompt: str | None = None  # For diagnose strategy
    reason: str = ""

    def __repr__(self) -> str:
        return f"RecoveryAction({self.strategy.value}, agent={self.agent_id}, reason={self.reason})"


# Fallback agent mappings - when an agent fails, try these instead
FALLBACK_AGENTS: dict[str, list[str]] = {
    "coder": ["reviewer", "architect"],  # If coder fails, have reviewer diagnose or architect redesign
    "tester": ["coder", "reviewer"],     # If tester fails, have coder check test setup or reviewer analyze
    "reviewer": ["architect"],            # If reviewer fails, have architect provide high-level review
    "architect": ["reviewer"],            # If architect fails, have reviewer analyze requirements
    "docs": ["coder", "reviewer"],       # If docs fails, have coder or reviewer help
    "devops": ["coder", "architect"],    # If devops fails, have coder or architect help
}

# Error patterns that suggest specific recovery strategies
ERROR_PATTERNS: list[tuple[str, FailureType, RecoveryStrategy]] = [
    ("timeout", FailureType.TIMEOUT, RecoveryStrategy.RETRY),
    ("timed out", FailureType.TIMEOUT, RecoveryStrategy.RETRY),
    ("rate limit", FailureType.API_ERROR, RecoveryStrategy.RETRY),
    ("rate_limit", FailureType.API_ERROR, RecoveryStrategy.RETRY),
    ("429", FailureType.API_ERROR, RecoveryStrategy.RETRY),
    ("connection", FailureType.API_ERROR, RecoveryStrategy.RETRY),
    ("network", FailureType.API_ERROR, RecoveryStrategy.RETRY),
    ("memory", FailureType.MEMORY_ERROR, RecoveryStrategy.RETRY),
    ("file not found", FailureType.TOOL_ERROR, RecoveryStrategy.DIAGNOSE),
    ("permission denied", FailureType.TOOL_ERROR, RecoveryStrategy.DIAGNOSE),
    ("syntax error", FailureType.AGENT_ERROR, RecoveryStrategy.FALLBACK_AGENT),
    ("compilation error", FailureType.AGENT_ERROR, RecoveryStrategy.FALLBACK_AGENT),
    ("test failed", FailureType.AGENT_ERROR, RecoveryStrategy.FALLBACK_AGENT),
]


class RecoveryConfig:
    """Configuration for error recovery."""

    def __init__(
        self,
        max_retries: int = 3,
        base_delay_seconds: float = 2.0,
        max_delay_seconds: float = 30.0,
        timeout_seconds: float = 300.0,  # 5 minutes default
        enable_fallback: bool = True,
        enable_diagnosis: bool = True,
    ):
        self.max_retries = max_retries
        self.base_delay_seconds = base_delay_seconds
        self.max_delay_seconds = max_delay_seconds
        self.timeout_seconds = timeout_seconds
        self.enable_fallback = enable_fallback
        self.enable_diagnosis = enable_diagnosis


# Default configuration
default_recovery_config = RecoveryConfig()


class FailureLogger:
    """Logs and tracks agent failures for debugging."""

    def __init__(self, max_history: int = 100):
        self._failures: list[FailureContext] = []
        self._max_history = max_history

    def log_failure(self, failure: FailureContext) -> None:
        """Log a failure with full context."""
        # Add to history
        self._failures.append(failure)
        if len(self._failures) > self._max_history:
            self._failures = self._failures[-self._max_history:]

        # Log to standard logger with context
        logger.error(
            f"Agent failure: {failure.agent_id} - {failure.failure_type.value}\n"
            f"  Task: {failure.task_description[:100]}...\n"
            f"  Error: {failure.error_message}\n"
            f"  Attempt: {failure.attempt}/{failure.max_attempts}\n"
            f"  Duration: {failure.duration_seconds:.1f}s\n"
            f"  Goals: {failure.goals_completed}/{failure.goals_total}\n"
            f"  Checkpoint: {failure.last_checkpoint or 'none'}"
        )

        if failure.stack_trace:
            logger.debug(f"Stack trace for {failure.task_id}:\n{failure.stack_trace}")

    def get_recent_failures(
        self,
        agent_id: str | None = None,
        failure_type: FailureType | None = None,
        limit: int = 20,
    ) -> list[FailureContext]:
        """Get recent failures with optional filters."""
        failures = self._failures

        if agent_id:
            failures = [f for f in failures if f.agent_id == agent_id]
        if failure_type:
            failures = [f for f in failures if f.failure_type == failure_type]

        return failures[-limit:]

    def get_failure_stats(self) -> dict[str, Any]:
        """Get statistics about recent failures."""
        if not self._failures:
            return {"total": 0}

        by_agent: dict[str, int] = {}
        by_type: dict[str, int] = {}
        retry_successes = 0
        total_retries = 0

        for f in self._failures:
            by_agent[f.agent_id] = by_agent.get(f.agent_id, 0) + 1
            by_type[f.failure_type.value] = by_type.get(f.failure_type.value, 0) + 1
            if f.attempt > 1:
                total_retries += 1
                # Can't track success from here, would need task outcome

        return {
            "total": len(self._failures),
            "by_agent": by_agent,
            "by_type": by_type,
            "total_retries": total_retries,
        }


# Global failure logger
failure_logger = FailureLogger()


def classify_error(error: str) -> tuple[FailureType, RecoveryStrategy]:
    """Classify an error and suggest initial recovery strategy."""
    error_lower = error.lower()

    for pattern, failure_type, strategy in ERROR_PATTERNS:
        if pattern in error_lower:
            return failure_type, strategy

    return FailureType.UNKNOWN, RecoveryStrategy.RETRY


def determine_recovery_action(
    failure: FailureContext,
    config: RecoveryConfig = default_recovery_config,
) -> RecoveryAction:
    """Determine the best recovery action for a failure.

    Args:
        failure: The failure context
        config: Recovery configuration

    Returns:
        RecoveryAction describing what to do next
    """
    failure_type, suggested_strategy = classify_error(failure.error_message)
    failure.failure_type = failure_type

    # If we haven't exhausted retries and error is retriable
    if failure.attempt < config.max_retries:
        if suggested_strategy == RecoveryStrategy.RETRY:
            # Exponential backoff
            delay = min(
                config.base_delay_seconds * (2 ** (failure.attempt - 1)),
                config.max_delay_seconds
            )
            return RecoveryAction(
                strategy=RecoveryStrategy.RETRY,
                delay_seconds=delay,
                reason=f"Retriable error ({failure_type.value}), attempt {failure.attempt + 1}/{config.max_retries}"
            )

    # Try fallback agent if enabled and available
    if config.enable_fallback and failure.attempt >= config.max_retries:
        fallback_agents = FALLBACK_AGENTS.get(failure.agent_id, [])
        if fallback_agents:
            fallback_agent = fallback_agents[0]
            return RecoveryAction(
                strategy=RecoveryStrategy.FALLBACK_AGENT,
                agent_id=fallback_agent,
                modified_prompt=_create_fallback_prompt(failure, fallback_agent),
                reason=f"Max retries exceeded, falling back to {fallback_agent}"
            )

    # Try diagnosis if enabled
    if config.enable_diagnosis and failure.attempt >= config.max_retries:
        return RecoveryAction(
            strategy=RecoveryStrategy.DIAGNOSE,
            agent_id="reviewer",
            diagnostic_prompt=_create_diagnostic_prompt(failure),
            reason="Max retries exceeded, requesting diagnosis"
        )

    # Final fallback: abort
    return RecoveryAction(
        strategy=RecoveryStrategy.ABORT,
        reason=f"No recovery possible after {failure.attempt} attempts"
    )


def _create_fallback_prompt(failure: FailureContext, fallback_agent: str) -> str:
    """Create a prompt for a fallback agent."""
    if fallback_agent == "reviewer":
        return f"""A task failed and needs your analysis to diagnose the issue.

**Original Task:**
{failure.task_description}

**Error:**
{failure.error_message}

**Progress Before Failure:**
- Goals completed: {failure.goals_completed}/{failure.goals_total}
- Last checkpoint: {failure.last_checkpoint or 'none'}

**Partial Response (if any):**
{failure.response_so_far[:1000] if failure.response_so_far else 'No response collected'}

Please analyze:
1. What likely caused this failure?
2. What needs to be fixed before retrying?
3. Provide specific recommendations."""

    elif fallback_agent == "architect":
        return f"""A task failed and may need architectural changes.

**Original Task:**
{failure.task_description}

**Error:**
{failure.error_message}

**Failure Type:** {failure.failure_type.value}

Please provide:
1. Analysis of why this approach failed
2. Alternative approach or architecture
3. Specific steps to implement the alternative"""

    else:
        return f"""A previous attempt at this task failed. Please try a different approach.

**Task:**
{failure.task_description}

**Previous Error:**
{failure.error_message}

**What to avoid:**
The previous approach resulted in: {failure.failure_type.value}

Please attempt this task with a different strategy."""


def _create_diagnostic_prompt(failure: FailureContext) -> str:
    """Create a diagnostic prompt for analyzing failures."""
    return f"""**DIAGNOSTIC REQUEST**

A subagent task has failed repeatedly and needs analysis.

**Task:** {failure.task_description}

**Agent:** {failure.agent_id}
**Attempts:** {failure.attempt}
**Failure Type:** {failure.failure_type.value}
**Error:** {failure.error_message}

**Progress:**
- Goals completed: {failure.goals_completed}/{failure.goals_total}
- Last checkpoint: {failure.last_checkpoint or 'none'}
- Duration: {failure.duration_seconds:.1f}s

**Partial Output:**
{failure.response_so_far[:2000] if failure.response_so_far else 'No output captured'}

**Please analyze:**
1. Root cause of the failure
2. Whether this is a transient or permanent issue
3. Recommended fix or workaround
4. Whether the task should be retried, modified, or abandoned"""


async def execute_with_retry(
    work_fn: Callable[[], Coroutine[Any, Any, Any]],
    task_id: str,
    agent_id: str,
    task_description: str,
    config: RecoveryConfig = default_recovery_config,
    on_retry: Callable[[int, float], Coroutine[Any, Any, None]] | None = None,
    on_failure: Callable[[FailureContext], Coroutine[Any, Any, None]] | None = None,
) -> tuple[Any, list[FailureContext]]:
    """Execute a function with retry logic.

    Args:
        work_fn: Async function to execute
        task_id: Task identifier for logging
        agent_id: Agent running the task
        task_description: Description of the task
        config: Recovery configuration
        on_retry: Callback before each retry (attempt, delay)
        on_failure: Callback on each failure

    Returns:
        Tuple of (result, list of failures encountered)
    """
    failures: list[FailureContext] = []
    last_error: Exception | None = None

    for attempt in range(1, config.max_retries + 1):
        started_at = datetime.now()

        try:
            # Execute with timeout
            result = await asyncio.wait_for(
                work_fn(),
                timeout=config.timeout_seconds
            )
            return result, failures

        except asyncio.TimeoutError as e:
            last_error = e
            error_msg = f"Task timed out after {config.timeout_seconds}s"
            failure_type = FailureType.TIMEOUT

        except asyncio.CancelledError:
            raise  # Don't retry cancelled tasks

        except Exception as e:
            last_error = e
            error_msg = str(e)
            failure_type, _ = classify_error(error_msg)

        # Create failure context
        failed_at = datetime.now()
        failure = FailureContext(
            task_id=task_id,
            agent_id=agent_id,
            task_description=task_description,
            failure_type=failure_type,
            error_message=error_msg,
            attempt=attempt,
            max_attempts=config.max_retries,
            started_at=started_at,
            failed_at=failed_at,
            duration_seconds=(failed_at - started_at).total_seconds(),
        )

        # Log and track
        failure_logger.log_failure(failure)
        failures.append(failure)

        if on_failure:
            await on_failure(failure)

        # Determine recovery action
        action = determine_recovery_action(failure, config)

        if action.strategy == RecoveryStrategy.RETRY and attempt < config.max_retries:
            logger.info(f"Retrying task {task_id} in {action.delay_seconds}s (attempt {attempt + 1})")

            if on_retry:
                await on_retry(attempt + 1, action.delay_seconds)

            await asyncio.sleep(action.delay_seconds)
            continue

        elif action.strategy == RecoveryStrategy.ABORT:
            break

    # All retries exhausted
    raise last_error or Exception(f"Task failed after {config.max_retries} attempts")


async def execute_with_timeout(
    work_fn: Callable[[], Coroutine[Any, Any, Any]],
    timeout_seconds: float,
    task_id: str = "unknown",
) -> Any:
    """Execute a function with timeout.

    Args:
        work_fn: Async function to execute
        timeout_seconds: Maximum execution time
        task_id: Task identifier for logging

    Returns:
        Result of work_fn

    Raises:
        asyncio.TimeoutError: If timeout exceeded
    """
    try:
        return await asyncio.wait_for(work_fn(), timeout=timeout_seconds)
    except asyncio.TimeoutError:
        logger.error(f"Task {task_id} timed out after {timeout_seconds}s")
        raise
