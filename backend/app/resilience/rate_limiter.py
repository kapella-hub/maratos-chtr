"""Rate limiter implementation for API and service call protection."""

import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)


class RateLimitError(Exception):
    """Raised when rate limit is exceeded."""

    def __init__(self, name: str, retry_after: float, limit_type: str):
        self.name = name
        self.retry_after = retry_after
        self.limit_type = limit_type
        super().__init__(
            f"Rate limit '{name}' exceeded ({limit_type}), retry after {retry_after:.1f}s"
        )


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting."""

    # Token bucket parameters
    requests_per_second: float = 10.0
    burst_size: int = 20

    # Sliding window parameters (optional additional limits)
    max_per_minute: int | None = None
    max_per_hour: int | None = None

    # Cooldown between requests (optional)
    min_interval_seconds: float = 0.0


@dataclass
class RateLimiter:
    """Token bucket rate limiter with sliding window support.

    Features:
    - Token bucket for smooth rate limiting
    - Optional sliding window limits (per minute, per hour)
    - Optional minimum interval between requests
    - Async-safe with proper locking

    Usage:
        limiter = RateLimiter("api_calls", RateLimitConfig(requests_per_second=5))
        try:
            await limiter.acquire()
            # Make API call
        except RateLimitError as e:
            # Handle rate limit
            await asyncio.sleep(e.retry_after)
    """

    name: str
    config: RateLimitConfig = field(default_factory=RateLimitConfig)

    # Token bucket state
    _tokens: float = field(default=0, init=False)
    _last_refill: float = field(default=0, init=False)

    # Sliding window state
    _call_history: list[float] = field(default_factory=list, init=False)
    _last_call_time: float = field(default=0, init=False)

    # Metrics
    _total_requests: int = field(default=0, init=False)
    _total_limited: int = field(default=0, init=False)

    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)

    def __post_init__(self) -> None:
        self._tokens = float(self.config.burst_size)
        self._last_refill = time.time()

    async def acquire(self, tokens: int = 1) -> bool:
        """Acquire tokens from the rate limiter.

        Args:
            tokens: Number of tokens to acquire (default 1)

        Returns:
            True if tokens acquired

        Raises:
            RateLimitError: If rate limit exceeded
        """
        async with self._lock:
            now = time.time()
            self._total_requests += 1

            # Check minimum interval
            if self.config.min_interval_seconds > 0:
                elapsed = now - self._last_call_time
                if elapsed < self.config.min_interval_seconds:
                    self._total_limited += 1
                    retry_after = self.config.min_interval_seconds - elapsed
                    raise RateLimitError(self.name, retry_after, "min_interval")

            # Refill tokens
            self._refill_tokens(now)

            # Check token bucket
            if self._tokens < tokens:
                self._total_limited += 1
                retry_after = (tokens - self._tokens) / self.config.requests_per_second
                raise RateLimitError(self.name, retry_after, "token_bucket")

            # Check sliding window limits
            self._cleanup_history(now)

            if self.config.max_per_minute is not None:
                minute_ago = now - 60
                calls_last_minute = sum(1 for t in self._call_history if t > minute_ago)
                if calls_last_minute >= self.config.max_per_minute:
                    self._total_limited += 1
                    oldest_in_window = min(t for t in self._call_history if t > minute_ago)
                    retry_after = 60 - (now - oldest_in_window)
                    raise RateLimitError(self.name, retry_after, "per_minute")

            if self.config.max_per_hour is not None:
                hour_ago = now - 3600
                calls_last_hour = sum(1 for t in self._call_history if t > hour_ago)
                if calls_last_hour >= self.config.max_per_hour:
                    self._total_limited += 1
                    oldest_in_window = min(t for t in self._call_history if t > hour_ago)
                    retry_after = 3600 - (now - oldest_in_window)
                    raise RateLimitError(self.name, retry_after, "per_hour")

            # Consume tokens and record call
            self._tokens -= tokens
            self._call_history.append(now)
            self._last_call_time = now

            return True

    async def wait_and_acquire(self, tokens: int = 1, max_wait: float = 30.0) -> bool:
        """Wait for tokens to become available, then acquire.

        Args:
            tokens: Number of tokens to acquire
            max_wait: Maximum time to wait in seconds

        Returns:
            True if acquired, False if max_wait exceeded
        """
        start = time.time()
        while time.time() - start < max_wait:
            try:
                return await self.acquire(tokens)
            except RateLimitError as e:
                wait_time = min(e.retry_after, max_wait - (time.time() - start))
                if wait_time <= 0:
                    return False
                await asyncio.sleep(wait_time)
        return False

    def _refill_tokens(self, now: float) -> None:
        """Refill tokens based on elapsed time (called under lock)."""
        elapsed = now - self._last_refill
        new_tokens = elapsed * self.config.requests_per_second
        self._tokens = min(self.config.burst_size, self._tokens + new_tokens)
        self._last_refill = now

    def _cleanup_history(self, now: float) -> None:
        """Remove old entries from call history (called under lock)."""
        # Keep only last hour of history
        hour_ago = now - 3600
        self._call_history = [t for t in self._call_history if t > hour_ago]

    def get_status(self) -> dict[str, Any]:
        """Get current rate limiter status."""
        now = time.time()
        minute_ago = now - 60
        hour_ago = now - 3600

        return {
            "name": self.name,
            "tokens_available": round(self._tokens, 2),
            "burst_size": self.config.burst_size,
            "requests_per_second": self.config.requests_per_second,
            "calls_last_minute": sum(1 for t in self._call_history if t > minute_ago),
            "max_per_minute": self.config.max_per_minute,
            "calls_last_hour": sum(1 for t in self._call_history if t > hour_ago),
            "max_per_hour": self.config.max_per_hour,
            "total_requests": self._total_requests,
            "total_limited": self._total_limited,
            "limit_rate": round(self._total_limited / max(1, self._total_requests), 3),
        }


class RateLimiterRegistry:
    """Registry for managing rate limiters."""

    def __init__(self) -> None:
        self._limiters: dict[str, RateLimiter] = {}

    def get_or_create(
        self,
        name: str,
        config: RateLimitConfig | None = None,
    ) -> RateLimiter:
        """Get or create a rate limiter."""
        if name not in self._limiters:
            self._limiters[name] = RateLimiter(
                name=name,
                config=config or RateLimitConfig(),
            )
        return self._limiters[name]

    def get(self, name: str) -> RateLimiter | None:
        """Get a rate limiter by name."""
        return self._limiters.get(name)

    def list_all(self) -> list[dict[str, Any]]:
        """List all rate limiters with their status."""
        return [l.get_status() for l in self._limiters.values()]


# Global registry
rate_limiter_registry = RateLimiterRegistry()
