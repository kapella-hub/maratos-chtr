"""Tool executor with audit logging, metrics, rate limiting, and guardrails enforcement.

All tool execution MUST go through this executor to ensure consistent enforcement of:
- Tool allowlists per agent
- Filesystem write jail
- Budget limits
- Diff-first approval
- Audit logging
"""

import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from app.tools.base import Tool, ToolResult, registry

logger = logging.getLogger(__name__)

# Guardrails integration - lazy import to avoid circular dependencies
_guardrails_checked = False
_guardrails_available = False
_GuardrailsEnforcer = None


def _ensure_guardrails():
    """Lazy import guardrails to avoid circular dependencies."""
    global _guardrails_checked, _guardrails_available, _GuardrailsEnforcer
    if _guardrails_checked:
        return _guardrails_available

    _guardrails_checked = True
    try:
        from app.guardrails import GuardrailsEnforcer
        _GuardrailsEnforcer = GuardrailsEnforcer
        _guardrails_available = True
    except ImportError:
        logger.warning("Guardrails module not available, running without enforcement")
        _guardrails_available = False

    return _guardrails_available


@dataclass
class ToolMetrics:
    """Metrics for a single tool."""

    tool_id: str
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    total_duration_ms: float = 0.0
    last_called_at: datetime | None = None

    @property
    def success_rate(self) -> float:
        if self.total_calls == 0:
            return 0.0
        return self.successful_calls / self.total_calls

    @property
    def avg_duration_ms(self) -> float:
        if self.total_calls == 0:
            return 0.0
        return self.total_duration_ms / self.total_calls

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_id": self.tool_id,
            "total_calls": self.total_calls,
            "successful_calls": self.successful_calls,
            "failed_calls": self.failed_calls,
            "success_rate": round(self.success_rate, 3),
            "avg_duration_ms": round(self.avg_duration_ms, 2),
            "total_duration_ms": round(self.total_duration_ms, 2),
            "last_called_at": self.last_called_at.isoformat() if self.last_called_at else None,
        }


@dataclass
class ToolRateLimit:
    """Rate limit configuration for a tool."""

    max_calls_per_minute: int = 60
    max_calls_per_hour: int = 1000
    cooldown_seconds: float = 0.0  # Minimum time between calls


class ToolExecutor:
    """Centralized tool executor with audit, metrics, and rate limiting.

    All tool executions should go through this executor for:
    - Audit logging
    - Metrics collection
    - Rate limiting
    - Error handling
    """

    def __init__(self) -> None:
        self._metrics: dict[str, ToolMetrics] = {}
        self._rate_limits: dict[str, ToolRateLimit] = {}
        self._call_history: dict[str, list[datetime]] = defaultdict(list)
        self._last_call_time: dict[str, float] = {}
        self._lock = asyncio.Lock()

        # Default rate limits for sensitive tools
        self._rate_limits["shell"] = ToolRateLimit(
            max_calls_per_minute=30,
            max_calls_per_hour=500,
            cooldown_seconds=0.5,
        )
        self._rate_limits["filesystem"] = ToolRateLimit(
            max_calls_per_minute=100,
            max_calls_per_hour=2000,
        )

    def set_rate_limit(self, tool_id: str, limit: ToolRateLimit) -> None:
        """Set rate limit for a tool."""
        self._rate_limits[tool_id] = limit

    def _get_metrics(self, tool_id: str) -> ToolMetrics:
        """Get or create metrics for a tool."""
        if tool_id not in self._metrics:
            self._metrics[tool_id] = ToolMetrics(tool_id=tool_id)
        return self._metrics[tool_id]

    def _check_rate_limit(self, tool_id: str) -> tuple[bool, str | None]:
        """Check if tool call is within rate limits.

        Returns (allowed, error_message).
        """
        limit = self._rate_limits.get(tool_id)
        if not limit:
            return True, None

        now = datetime.now()

        # Check cooldown
        last_call = self._last_call_time.get(tool_id, 0)
        if limit.cooldown_seconds > 0:
            elapsed = time.time() - last_call
            if elapsed < limit.cooldown_seconds:
                return False, f"Cooldown: wait {limit.cooldown_seconds - elapsed:.1f}s"

        # Clean old history
        history = self._call_history[tool_id]
        minute_ago = now - timedelta(minutes=1)
        hour_ago = now - timedelta(hours=1)
        self._call_history[tool_id] = [t for t in history if t > hour_ago]

        # Check per-minute limit
        calls_last_minute = sum(1 for t in self._call_history[tool_id] if t > minute_ago)
        if calls_last_minute >= limit.max_calls_per_minute:
            return False, f"Rate limit: {limit.max_calls_per_minute}/min exceeded"

        # Check per-hour limit
        if len(self._call_history[tool_id]) >= limit.max_calls_per_hour:
            return False, f"Rate limit: {limit.max_calls_per_hour}/hour exceeded"

        return True, None

    async def execute(
        self,
        tool_id: str,
        session_id: str | None = None,
        task_id: str | None = None,
        agent_id: str | None = None,
        enforcer: "GuardrailsEnforcer | None" = None,
        skip_guardrails: bool = False,
        **kwargs: Any,
    ) -> ToolResult:
        """Execute a tool with guardrails enforcement, audit logging, and metrics.

        IMPORTANT: All tool execution should go through this method to ensure
        consistent enforcement of security policies.

        Args:
            tool_id: The tool to execute
            session_id: Optional session ID for audit
            task_id: Optional task ID for audit
            agent_id: Optional agent ID for policy lookup
            enforcer: Pre-configured GuardrailsEnforcer (recommended)
            skip_guardrails: DANGEROUS - skip guardrails (only for internal use)
            **kwargs: Tool parameters

        Returns:
            ToolResult from the tool execution
        """
        # Create enforcer if not provided and guardrails available
        if enforcer is None and not skip_guardrails and _ensure_guardrails():
            if agent_id:
                enforcer = _GuardrailsEnforcer.for_agent(
                    agent_id=agent_id,
                    session_id=session_id,
                    task_id=task_id,
                )
            else:
                # Use default restrictive policy for unknown callers
                enforcer = _GuardrailsEnforcer.default(session_id=session_id)

        # Run guardrails check
        enforcement_result = None
        if enforcer and not skip_guardrails:
            enforcement_result = await enforcer.check_tool_execution(tool_id, kwargs)
            if not enforcement_result.allowed:
                logger.warning(f"Tool {tool_id} blocked by guardrails: {enforcement_result.error}")
                return ToolResult(
                    success=False,
                    output="",
                    error=enforcement_result.error,
                )

        # Check rate limit
        async with self._lock:
            allowed, error = self._check_rate_limit(tool_id)
            if not allowed:
                logger.warning(f"Tool {tool_id} rate limited: {error}")
                return ToolResult(success=False, output="", error=error)

            # Record call time
            self._call_history[tool_id].append(datetime.now())
            self._last_call_time[tool_id] = time.time()

        # Get tool
        tool = registry.get(tool_id)
        if not tool:
            error = f"Tool not found: {tool_id}"
            return ToolResult(success=False, output="", error=error)

        # Execute with timing
        start_time = time.time()
        try:
            result = await tool.execute(**kwargs)
            duration_ms = (time.time() - start_time) * 1000

            # Update metrics
            metrics = self._get_metrics(tool_id)
            metrics.total_calls += 1
            metrics.total_duration_ms += duration_ms
            metrics.last_called_at = datetime.now()
            if result.success:
                metrics.successful_calls += 1
            else:
                metrics.failed_calls += 1

            # Record in enforcer
            if enforcer and enforcement_result:
                await enforcer.record_tool_execution(
                    tool_id, kwargs, result, duration_ms, enforcement_result
                )

            return result

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            error_msg = str(e)

            # Update metrics
            metrics = self._get_metrics(tool_id)
            metrics.total_calls += 1
            metrics.failed_calls += 1
            metrics.total_duration_ms += duration_ms
            metrics.last_called_at = datetime.now()

            logger.error(f"Tool {tool_id} execution error: {e}", exc_info=True)

            result = ToolResult(success=False, output="", error=error_msg)

            # Record in enforcer
            if enforcer and enforcement_result:
                await enforcer.record_tool_execution(
                    tool_id, kwargs, result, duration_ms, enforcement_result
                )

            return result

    def get_metrics(self, tool_id: str | None = None) -> dict[str, Any]:
        """Get tool metrics.

        Args:
            tool_id: Optional specific tool, or all tools if None

        Returns:
            Metrics dictionary
        """
        if tool_id:
            metrics = self._metrics.get(tool_id)
            return metrics.to_dict() if metrics else {}

        return {
            "tools": {tid: m.to_dict() for tid, m in self._metrics.items()},
            "total_calls": sum(m.total_calls for m in self._metrics.values()),
            "total_errors": sum(m.failed_calls for m in self._metrics.values()),
        }

    def get_rate_limit_status(self, tool_id: str) -> dict[str, Any]:
        """Get current rate limit status for a tool."""
        limit = self._rate_limits.get(tool_id)
        if not limit:
            return {"limited": False, "message": "No rate limit configured"}

        now = datetime.now()
        minute_ago = now - timedelta(minutes=1)
        hour_ago = now - timedelta(hours=1)

        history = self._call_history.get(tool_id, [])
        calls_last_minute = sum(1 for t in history if t > minute_ago)
        calls_last_hour = sum(1 for t in history if t > hour_ago)

        return {
            "limited": True,
            "calls_last_minute": calls_last_minute,
            "max_per_minute": limit.max_calls_per_minute,
            "calls_last_hour": calls_last_hour,
            "max_per_hour": limit.max_calls_per_hour,
            "cooldown_seconds": limit.cooldown_seconds,
        }


# Global tool executor
tool_executor = ToolExecutor()
