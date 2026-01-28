"""API endpoints for diff-first approval workflow.

Provides endpoints for:
- Listing pending approvals
- Approving/denying requests
- Getting approval details
- SSE stream for real-time approval notifications
"""

import asyncio
import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.guardrails.diff_approval import (
    diff_approval_manager,
    ApprovalStatus,
    PendingApproval,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/approvals")


# =============================================================================
# Pydantic Models
# =============================================================================


class ApprovalResponse(BaseModel):
    """Response model for an approval request."""

    id: str
    action_type: str
    session_id: str
    agent_id: str
    task_id: str | None
    file_path: str | None
    diff: str | None
    content_hash: str | None
    command: str | None
    workdir: str | None
    status: str
    created_at: str
    expires_at: str | None
    approved_by: str | None
    approval_note: str | None

    # Computed fields for UI
    is_file_operation: bool = False
    is_shell_operation: bool = False
    affected_paths: list[str] = Field(default_factory=list)

    @classmethod
    def from_pending(cls, approval: PendingApproval) -> "ApprovalResponse":
        """Create from PendingApproval."""
        affected_paths = []
        if approval.file_path:
            affected_paths.append(approval.file_path)

        return cls(
            id=approval.id,
            action_type=approval.action_type,
            session_id=approval.session_id,
            agent_id=approval.agent_id,
            task_id=approval.task_id,
            file_path=approval.file_path,
            diff=approval.diff,
            content_hash=approval.content_hash,
            command=approval.command,
            workdir=approval.workdir,
            status=approval.status.value,
            created_at=approval.created_at.isoformat(),
            expires_at=approval.expires_at.isoformat() if approval.expires_at else None,
            approved_by=approval.approved_by,
            approval_note=approval.approval_note,
            is_file_operation=approval.action_type in ("write", "delete"),
            is_shell_operation=approval.action_type == "shell",
            affected_paths=affected_paths,
        )


class ApprovalListResponse(BaseModel):
    """Response for listing approvals."""

    approvals: list[ApprovalResponse]
    total: int
    pending_count: int


class ApproveRequest(BaseModel):
    """Request to approve an action."""

    approved_by: str = "user"
    note: str | None = None


class DenyRequest(BaseModel):
    """Request to deny an action."""

    denied_by: str = "user"
    reason: str | None = None


class ApprovalActionResponse(BaseModel):
    """Response after approve/deny action."""

    success: bool
    approval_id: str
    new_status: str
    message: str


# =============================================================================
# API Endpoints
# =============================================================================


@router.get("", response_model=ApprovalListResponse)
async def list_approvals(
    status: str | None = Query(None, description="Filter by status: pending, approved, denied, expired"),
    session_id: str | None = Query(None, description="Filter by session ID"),
    limit: int = Query(50, ge=1, le=200),
) -> ApprovalListResponse:
    """List approval requests with optional filters.

    Returns approvals sorted by created_at descending (newest first).
    """
    # Get all approvals from manager
    all_approvals = list(diff_approval_manager._pending.values())

    # Filter by session
    if session_id:
        all_approvals = [a for a in all_approvals if a.session_id == session_id]

    # Filter by status
    if status:
        try:
            status_enum = ApprovalStatus(status)
            all_approvals = [a for a in all_approvals if a.status == status_enum]
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

    # Sort by created_at descending
    all_approvals.sort(key=lambda a: a.created_at, reverse=True)

    # Count pending
    pending_count = sum(1 for a in diff_approval_manager._pending.values()
                        if a.status == ApprovalStatus.PENDING)

    # Limit
    limited = all_approvals[:limit]

    return ApprovalListResponse(
        approvals=[ApprovalResponse.from_pending(a) for a in limited],
        total=len(all_approvals),
        pending_count=pending_count,
    )


@router.get("/pending", response_model=ApprovalListResponse)
async def list_pending_approvals(
    session_id: str | None = Query(None, description="Filter by session ID"),
) -> ApprovalListResponse:
    """List only pending approval requests.

    Convenience endpoint for getting pending approvals.
    """
    pending = diff_approval_manager.get_pending(session_id=session_id)

    # Sort by created_at descending
    pending.sort(key=lambda a: a.created_at, reverse=True)

    return ApprovalListResponse(
        approvals=[ApprovalResponse.from_pending(a) for a in pending],
        total=len(pending),
        pending_count=len(pending),
    )


@router.get("/{approval_id}", response_model=ApprovalResponse)
async def get_approval(approval_id: str) -> ApprovalResponse:
    """Get details of a specific approval request."""
    approval = diff_approval_manager.get_approval(approval_id)
    if not approval:
        raise HTTPException(status_code=404, detail=f"Approval {approval_id} not found")

    return ApprovalResponse.from_pending(approval)


@router.post("/{approval_id}/approve", response_model=ApprovalActionResponse)
async def approve_request(
    approval_id: str,
    request: ApproveRequest,
) -> ApprovalActionResponse:
    """Approve a pending action.

    After approval, the action will be executed with the exact
    diff/command that was approved.
    """
    approval = diff_approval_manager.get_approval(approval_id)
    if not approval:
        raise HTTPException(status_code=404, detail=f"Approval {approval_id} not found")

    if approval.status != ApprovalStatus.PENDING:
        raise HTTPException(
            status_code=400,
            detail=f"Approval is not pending (current status: {approval.status.value})"
        )

    success = diff_approval_manager.approve(
        approval_id,
        approved_by=request.approved_by,
        note=request.note,
    )

    if not success:
        raise HTTPException(status_code=500, detail="Failed to approve request")

    logger.info(f"Approval {approval_id} approved by {request.approved_by}")

    return ApprovalActionResponse(
        success=True,
        approval_id=approval_id,
        new_status=ApprovalStatus.APPROVED.value,
        message=f"Action approved by {request.approved_by}",
    )


@router.post("/{approval_id}/deny", response_model=ApprovalActionResponse)
async def deny_request(
    approval_id: str,
    request: DenyRequest,
) -> ApprovalActionResponse:
    """Deny a pending action.

    The action will not be executed.
    """
    approval = diff_approval_manager.get_approval(approval_id)
    if not approval:
        raise HTTPException(status_code=404, detail=f"Approval {approval_id} not found")

    if approval.status != ApprovalStatus.PENDING:
        raise HTTPException(
            status_code=400,
            detail=f"Approval is not pending (current status: {approval.status.value})"
        )

    success = diff_approval_manager.reject(
        approval_id,
        rejected_by=request.denied_by,
        reason=request.reason,
    )

    if not success:
        raise HTTPException(status_code=500, detail="Failed to deny request")

    logger.info(f"Approval {approval_id} denied by {request.denied_by}: {request.reason}")

    return ApprovalActionResponse(
        success=True,
        approval_id=approval_id,
        new_status=ApprovalStatus.REJECTED.value,
        message=f"Action denied by {request.denied_by}" + (f": {request.reason}" if request.reason else ""),
    )


@router.delete("/{approval_id}")
async def cancel_approval(approval_id: str) -> dict[str, Any]:
    """Cancel/expire a pending approval.

    Used when the requesting agent/task no longer needs the approval.
    """
    approval = diff_approval_manager.get_approval(approval_id)
    if not approval:
        raise HTTPException(status_code=404, detail=f"Approval {approval_id} not found")

    if approval.status == ApprovalStatus.PENDING:
        approval.status = ApprovalStatus.EXPIRED
        # Signal waiting tasks
        event = diff_approval_manager._approval_events.get(approval_id)
        if event:
            event.set()

    return {"success": True, "message": "Approval cancelled"}


@router.get("/stream/events")
async def approval_events_stream(
    session_id: str | None = Query(None, description="Filter by session ID"),
):
    """Server-Sent Events stream for real-time approval notifications.

    Events:
    - approval_requested: New approval request created
    - approval_resolved: Approval was approved/denied/expired

    Usage:
        const es = new EventSource('/api/approvals/stream/events?session_id=xxx');
        es.onmessage = (event) => {
            const data = JSON.parse(event.data);
            // Handle approval event
        };
    """
    async def event_generator():
        """Generate SSE events for approval changes."""
        # Track known approvals to detect changes
        known_approvals: dict[str, str] = {}  # id -> status

        # Register callback for new approvals
        new_approvals_queue: asyncio.Queue[PendingApproval] = asyncio.Queue()

        async def on_new_approval(approval: PendingApproval):
            if session_id is None or approval.session_id == session_id:
                await new_approvals_queue.put(approval)

        diff_approval_manager.register_approval_callback(on_new_approval)

        try:
            # Send initial pending approvals
            pending = diff_approval_manager.get_pending(session_id=session_id)
            for approval in pending:
                known_approvals[approval.id] = approval.status.value
                data = ApprovalResponse.from_pending(approval).model_dump_json()
                yield f"event: approval_requested\ndata: {data}\n\n"

            # Poll for changes
            while True:
                # Check for new approvals from callback
                try:
                    new_approval = await asyncio.wait_for(
                        new_approvals_queue.get(),
                        timeout=1.0
                    )
                    if new_approval.id not in known_approvals:
                        known_approvals[new_approval.id] = new_approval.status.value
                        data = ApprovalResponse.from_pending(new_approval).model_dump_json()
                        yield f"event: approval_requested\ndata: {data}\n\n"
                except asyncio.TimeoutError:
                    pass

                # Check for status changes
                current = list(diff_approval_manager._pending.values())
                if session_id:
                    current = [a for a in current if a.session_id == session_id]

                for approval in current:
                    old_status = known_approvals.get(approval.id)
                    new_status = approval.status.value

                    if old_status and old_status != new_status:
                        known_approvals[approval.id] = new_status
                        data = ApprovalResponse.from_pending(approval).model_dump_json()
                        yield f"event: approval_resolved\ndata: {data}\n\n"

                # Send heartbeat
                yield f": heartbeat\n\n"

        except asyncio.CancelledError:
            pass
        finally:
            # Unregister callback
            if on_new_approval in diff_approval_manager._on_approval_requested:
                diff_approval_manager._on_approval_requested.remove(on_new_approval)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/cleanup")
async def cleanup_expired() -> dict[str, Any]:
    """Clean up expired approval requests.

    Call periodically to clean up old approvals.
    """
    count = diff_approval_manager.cleanup_expired()
    return {"cleaned_up": count}
