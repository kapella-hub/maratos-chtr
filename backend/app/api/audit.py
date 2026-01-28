"""Audit log API endpoints."""

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.audit import audit_logger, AuditCategory

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/audit", tags=["audit"])


class AuditEventResponse(BaseModel):
    """Audit event response."""

    category: str
    action: str
    severity: str
    session_id: str | None
    agent_id: str | None
    task_id: str | None
    timestamp: str
    duration_ms: float | None
    success: bool
    error: str | None


class AuditStatsResponse(BaseModel):
    """Audit statistics response."""

    total_events: int
    events_by_category: dict[str, int]
    events_by_severity: dict[str, int]
    error_count: int
    buffer_size: int


@router.get("/events")
async def get_audit_events(
    limit: int = Query(default=100, ge=1, le=1000),
    category: str | None = Query(default=None),
    session_id: str | None = Query(default=None),
) -> list[AuditEventResponse]:
    """Get recent audit events from memory buffer.

    This endpoint returns events from the in-memory buffer (most recent events).
    For historical queries, use /audit/query endpoint.
    """
    # Parse category if provided
    cat_filter = None
    if category:
        try:
            cat_filter = AuditCategory(category)
        except ValueError:
            pass  # Invalid category, ignore filter

    events = audit_logger.get_recent_events(
        limit=limit,
        category=cat_filter,
        session_id=session_id,
    )

    return [
        AuditEventResponse(
            category=e.category.value,
            action=e.action,
            severity=e.severity.value,
            session_id=e.session_id,
            agent_id=e.agent_id,
            task_id=e.task_id,
            timestamp=e.timestamp.isoformat(),
            duration_ms=e.duration_ms,
            success=e.success,
            error=e.error,
        )
        for e in events
    ]


@router.get("/query")
async def query_audit_events(
    start_date: datetime | None = Query(default=None),
    end_date: datetime | None = Query(default=None),
    category: str | None = Query(default=None),
    session_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=10000),
) -> list[dict[str, Any]]:
    """Query audit events from log files.

    This endpoint queries persisted events from JSONL log files.
    Supports date range filtering and category/session filtering.
    """
    cat_filter = None
    if category:
        try:
            cat_filter = AuditCategory(category)
        except ValueError:
            pass

    events = await audit_logger.query_events(
        start_date=start_date,
        end_date=end_date,
        category=cat_filter,
        session_id=session_id,
        limit=limit,
    )

    return events


@router.get("/stats")
async def get_audit_stats() -> AuditStatsResponse:
    """Get audit statistics from recent events."""
    events = audit_logger.get_recent_events(limit=1000)

    events_by_category: dict[str, int] = {}
    events_by_severity: dict[str, int] = {}
    error_count = 0

    for e in events:
        cat = e.category.value
        sev = e.severity.value
        events_by_category[cat] = events_by_category.get(cat, 0) + 1
        events_by_severity[sev] = events_by_severity.get(sev, 0) + 1
        if not e.success:
            error_count += 1

    return AuditStatsResponse(
        total_events=len(events),
        events_by_category=events_by_category,
        events_by_severity=events_by_severity,
        error_count=error_count,
        buffer_size=len(audit_logger._buffer),
    )


@router.get("/categories")
async def get_audit_categories() -> list[str]:
    """Get available audit categories."""
    return [c.value for c in AuditCategory]
