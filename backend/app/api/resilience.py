"""Resilience API endpoints - circuit breakers and rate limiters."""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.resilience import circuit_breaker_registry, rate_limiter_registry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/resilience", tags=["resilience"])


class CircuitBreakerStatus(BaseModel):
    """Circuit breaker status response."""

    name: str
    state: str
    failure_count: int
    success_count: int
    total_calls: int
    total_failures: int
    total_rejections: int


class RateLimiterStatus(BaseModel):
    """Rate limiter status response."""

    name: str
    tokens_available: float
    burst_size: int
    requests_per_second: float
    calls_last_minute: int
    calls_last_hour: int
    total_requests: int
    total_limited: int
    limit_rate: float


@router.get("/circuit-breakers")
async def list_circuit_breakers() -> list[dict[str, Any]]:
    """List all circuit breakers with their status."""
    return circuit_breaker_registry.list_all()


@router.get("/circuit-breakers/{name}")
async def get_circuit_breaker(name: str) -> dict[str, Any]:
    """Get a specific circuit breaker status."""
    breaker = circuit_breaker_registry.get(name)
    if not breaker:
        raise HTTPException(status_code=404, detail=f"Circuit breaker not found: {name}")
    return breaker.get_status()


@router.post("/circuit-breakers/{name}/reset")
async def reset_circuit_breaker(name: str) -> dict[str, str]:
    """Manually reset a circuit breaker to closed state."""
    breaker = circuit_breaker_registry.get(name)
    if not breaker:
        raise HTTPException(status_code=404, detail=f"Circuit breaker not found: {name}")
    breaker.reset()
    return {"status": "reset", "name": name}


@router.post("/circuit-breakers/reset-all")
async def reset_all_circuit_breakers() -> dict[str, str]:
    """Reset all circuit breakers."""
    circuit_breaker_registry.reset_all()
    return {"status": "all_reset"}


@router.get("/rate-limiters")
async def list_rate_limiters() -> list[dict[str, Any]]:
    """List all rate limiters with their status."""
    return rate_limiter_registry.list_all()


@router.get("/rate-limiters/{name}")
async def get_rate_limiter(name: str) -> dict[str, Any]:
    """Get a specific rate limiter status."""
    limiter = rate_limiter_registry.get(name)
    if not limiter:
        raise HTTPException(status_code=404, detail=f"Rate limiter not found: {name}")
    return limiter.get_status()


@router.get("/status")
async def get_resilience_status() -> dict[str, Any]:
    """Get overall resilience status."""
    circuit_breakers = circuit_breaker_registry.list_all()
    rate_limiters = rate_limiter_registry.list_all()

    # Count open circuits
    open_circuits = sum(1 for cb in circuit_breakers if cb["state"] == "open")
    half_open_circuits = sum(1 for cb in circuit_breakers if cb["state"] == "half_open")

    # Calculate overall rate limit pressure
    total_limited = sum(rl["total_limited"] for rl in rate_limiters)
    total_requests = sum(rl["total_requests"] for rl in rate_limiters)
    overall_limit_rate = total_limited / max(1, total_requests)

    return {
        "healthy": open_circuits == 0,
        "circuit_breakers": {
            "total": len(circuit_breakers),
            "open": open_circuits,
            "half_open": half_open_circuits,
            "closed": len(circuit_breakers) - open_circuits - half_open_circuits,
        },
        "rate_limiters": {
            "total": len(rate_limiters),
            "total_requests": total_requests,
            "total_limited": total_limited,
            "overall_limit_rate": round(overall_limit_rate, 3),
        },
    }
