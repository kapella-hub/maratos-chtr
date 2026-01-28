"""Circuit breaker implementation for external service protection."""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Coroutine, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class CircuitState(str, Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject calls
    HALF_OPEN = "half_open"  # Testing if service recovered


class CircuitBreakerError(Exception):
    """Raised when circuit is open."""

    def __init__(self, name: str, state: CircuitState, retry_after: float):
        self.name = name
        self.state = state
        self.retry_after = retry_after
        super().__init__(f"Circuit '{name}' is {state.value}, retry after {retry_after:.1f}s")


@dataclass
class CircuitBreakerConfig:
    """Configuration for a circuit breaker."""

    failure_threshold: int = 5  # Failures before opening
    success_threshold: int = 3  # Successes in half-open before closing
    timeout_seconds: float = 30.0  # Time before transitioning to half-open
    half_open_max_calls: int = 3  # Max concurrent calls in half-open


@dataclass
class CircuitBreaker:
    """Circuit breaker for protecting external service calls.

    States:
    - CLOSED: Normal operation, calls pass through
    - OPEN: Too many failures, calls are rejected immediately
    - HALF_OPEN: Testing recovery, limited calls allowed

    Usage:
        breaker = CircuitBreaker("api_service")
        try:
            result = await breaker.call(async_function, *args, **kwargs)
        except CircuitBreakerError as e:
            # Handle circuit open
            pass
    """

    name: str
    config: CircuitBreakerConfig = field(default_factory=CircuitBreakerConfig)

    _state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    _failure_count: int = field(default=0, init=False)
    _success_count: int = field(default=0, init=False)
    _last_failure_time: float = field(default=0, init=False)
    _half_open_calls: int = field(default=0, init=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)

    # Metrics
    _total_calls: int = field(default=0, init=False)
    _total_failures: int = field(default=0, init=False)
    _total_rejections: int = field(default=0, init=False)
    _last_state_change: datetime = field(default_factory=datetime.now, init=False)

    @property
    def state(self) -> CircuitState:
        return self._state

    @property
    def is_closed(self) -> bool:
        return self._state == CircuitState.CLOSED

    @property
    def is_open(self) -> bool:
        return self._state == CircuitState.OPEN

    async def call(
        self,
        func: Callable[..., Coroutine[Any, Any, T]],
        *args: Any,
        **kwargs: Any,
    ) -> T:
        """Execute a function through the circuit breaker.

        Args:
            func: Async function to call
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            Result from the function

        Raises:
            CircuitBreakerError: If circuit is open
            Exception: Any exception from the function
        """
        async with self._lock:
            self._check_state_transition()

            if self._state == CircuitState.OPEN:
                retry_after = self._time_until_half_open()
                self._total_rejections += 1
                raise CircuitBreakerError(self.name, self._state, retry_after)

            if self._state == CircuitState.HALF_OPEN:
                if self._half_open_calls >= self.config.half_open_max_calls:
                    raise CircuitBreakerError(self.name, self._state, 1.0)
                self._half_open_calls += 1

        self._total_calls += 1

        try:
            result = await func(*args, **kwargs)
            await self._record_success()
            return result
        except Exception as e:
            await self._record_failure(e)
            raise

    async def _record_success(self) -> None:
        """Record a successful call."""
        async with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                self._half_open_calls -= 1

                if self._success_count >= self.config.success_threshold:
                    self._transition_to(CircuitState.CLOSED)
            else:
                # In closed state, reset failure count on success
                self._failure_count = 0

    async def _record_failure(self, error: Exception) -> None:
        """Record a failed call."""
        async with self._lock:
            self._total_failures += 1
            self._last_failure_time = time.time()

            if self._state == CircuitState.HALF_OPEN:
                self._half_open_calls -= 1
                self._transition_to(CircuitState.OPEN)
                logger.warning(f"Circuit '{self.name}' reopened after failure in half-open: {error}")
            else:
                self._failure_count += 1

                if self._failure_count >= self.config.failure_threshold:
                    self._transition_to(CircuitState.OPEN)
                    logger.warning(
                        f"Circuit '{self.name}' opened after {self._failure_count} failures"
                    )

    def _check_state_transition(self) -> None:
        """Check if state should transition (called under lock)."""
        if self._state == CircuitState.OPEN:
            if time.time() - self._last_failure_time >= self.config.timeout_seconds:
                self._transition_to(CircuitState.HALF_OPEN)
                logger.info(f"Circuit '{self.name}' transitioned to half-open")

    def _transition_to(self, new_state: CircuitState) -> None:
        """Transition to a new state (called under lock)."""
        old_state = self._state
        self._state = new_state
        self._last_state_change = datetime.now()

        if new_state == CircuitState.CLOSED:
            self._failure_count = 0
            self._success_count = 0
            logger.info(f"Circuit '{self.name}' closed")
        elif new_state == CircuitState.HALF_OPEN:
            self._success_count = 0
            self._half_open_calls = 0
        elif new_state == CircuitState.OPEN:
            self._success_count = 0

    def _time_until_half_open(self) -> float:
        """Calculate time until circuit transitions to half-open."""
        elapsed = time.time() - self._last_failure_time
        remaining = self.config.timeout_seconds - elapsed
        return max(0, remaining)

    def reset(self) -> None:
        """Manually reset the circuit to closed state."""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._half_open_calls = 0
        self._last_state_change = datetime.now()
        logger.info(f"Circuit '{self.name}' manually reset")

    def get_status(self) -> dict[str, Any]:
        """Get current circuit status."""
        return {
            "name": self.name,
            "state": self._state.value,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
            "total_calls": self._total_calls,
            "total_failures": self._total_failures,
            "total_rejections": self._total_rejections,
            "last_state_change": self._last_state_change.isoformat(),
            "time_until_half_open": self._time_until_half_open() if self._state == CircuitState.OPEN else None,
            "config": {
                "failure_threshold": self.config.failure_threshold,
                "success_threshold": self.config.success_threshold,
                "timeout_seconds": self.config.timeout_seconds,
            },
        }


class CircuitBreakerRegistry:
    """Registry for managing circuit breakers."""

    def __init__(self) -> None:
        self._breakers: dict[str, CircuitBreaker] = {}

    def get_or_create(
        self,
        name: str,
        config: CircuitBreakerConfig | None = None,
    ) -> CircuitBreaker:
        """Get or create a circuit breaker."""
        if name not in self._breakers:
            self._breakers[name] = CircuitBreaker(
                name=name,
                config=config or CircuitBreakerConfig(),
            )
        return self._breakers[name]

    def get(self, name: str) -> CircuitBreaker | None:
        """Get a circuit breaker by name."""
        return self._breakers.get(name)

    def list_all(self) -> list[dict[str, Any]]:
        """List all circuit breakers with their status."""
        return [b.get_status() for b in self._breakers.values()]

    def reset_all(self) -> None:
        """Reset all circuit breakers."""
        for breaker in self._breakers.values():
            breaker.reset()


# Global registry
circuit_breaker_registry = CircuitBreakerRegistry()
