"""Diff-first mode for high-impact actions.

Intercepts write/delete/shell operations, generates diffs or previews,
and queues them for user approval before execution.
"""

import asyncio
import difflib
import hashlib
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)


class ApprovalStatus(str, Enum):
    """Status of a pending approval."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    AUTO_APPROVED = "auto_approved"


@dataclass
class PendingApproval:
    """A pending approval request for a high-impact action."""

    id: str
    action_type: str  # write, delete, shell
    session_id: str
    agent_id: str
    task_id: str | None

    # For file operations
    file_path: str | None = None
    original_content: str | None = None
    new_content: str | None = None
    diff: str | None = None
    content_hash: str | None = None

    # For shell operations
    command: str | None = None
    workdir: str | None = None

    # Status tracking
    status: ApprovalStatus = ApprovalStatus.PENDING
    created_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: datetime | None = None
    approved_by: str | None = None
    approval_note: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "action_type": self.action_type,
            "session_id": self.session_id,
            "agent_id": self.agent_id,
            "task_id": self.task_id,
            "file_path": self.file_path,
            "diff": self.diff,
            "content_hash": self.content_hash,
            "command": self.command,
            "workdir": self.workdir,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "approved_by": self.approved_by,
            "approval_note": self.approval_note,
        }


class DiffApprovalManager:
    """Manages diff-first approval workflow for high-impact actions.

    Usage:
        manager = DiffApprovalManager()

        # Check if approval needed
        if manager.requires_approval(policy, "write", "/path/to/file"):
            # Create approval request
            approval = await manager.create_write_approval(
                session_id, agent_id, task_id,
                file_path, original_content, new_content
            )

            # Wait for approval (with timeout)
            try:
                await manager.wait_for_approval(approval.id, timeout=300)
            except ApprovalTimeoutError:
                # Handle timeout
                pass
    """

    def __init__(self):
        self._pending: dict[str, PendingApproval] = {}
        self._approval_events: dict[str, asyncio.Event] = {}
        self._on_approval_requested: list[Callable[[PendingApproval], Awaitable[None]]] = []

    def register_approval_callback(
        self,
        callback: Callable[[PendingApproval], Awaitable[None]],
    ) -> None:
        """Register a callback for when approval is requested."""
        self._on_approval_requested.append(callback)

    async def create_write_approval(
        self,
        session_id: str,
        agent_id: str,
        task_id: str | None,
        file_path: str,
        original_content: str | None,
        new_content: str,
        timeout_seconds: float = 300.0,
    ) -> PendingApproval:
        """Create an approval request for a file write operation."""
        approval_id = str(uuid.uuid4())

        # Generate diff
        diff = self._generate_diff(
            file_path,
            original_content or "",
            new_content,
        )

        # Hash the new content
        content_hash = hashlib.sha256(new_content.encode()).hexdigest()[:16]

        approval = PendingApproval(
            id=approval_id,
            action_type="write",
            session_id=session_id,
            agent_id=agent_id,
            task_id=task_id,
            file_path=file_path,
            original_content=original_content,
            new_content=new_content,
            diff=diff,
            content_hash=content_hash,
            expires_at=datetime.utcnow() + timedelta(seconds=timeout_seconds),
        )

        self._pending[approval_id] = approval
        self._approval_events[approval_id] = asyncio.Event()

        logger.info(
            f"Created write approval request {approval_id} for {file_path} "
            f"(session={session_id}, agent={agent_id})"
        )

        # Notify callbacks
        for callback in self._on_approval_requested:
            try:
                await callback(approval)
            except Exception as e:
                logger.error(f"Error in approval callback: {e}")

        return approval

    async def create_delete_approval(
        self,
        session_id: str,
        agent_id: str,
        task_id: str | None,
        file_path: str,
        original_content: str | None = None,
        timeout_seconds: float = 300.0,
    ) -> PendingApproval:
        """Create an approval request for a file delete operation."""
        approval_id = str(uuid.uuid4())

        approval = PendingApproval(
            id=approval_id,
            action_type="delete",
            session_id=session_id,
            agent_id=agent_id,
            task_id=task_id,
            file_path=file_path,
            original_content=original_content,
            expires_at=datetime.utcnow() + timedelta(seconds=timeout_seconds),
        )

        self._pending[approval_id] = approval
        self._approval_events[approval_id] = asyncio.Event()

        logger.info(
            f"Created delete approval request {approval_id} for {file_path}"
        )

        for callback in self._on_approval_requested:
            try:
                await callback(approval)
            except Exception as e:
                logger.error(f"Error in approval callback: {e}")

        return approval

    async def create_shell_approval(
        self,
        session_id: str,
        agent_id: str,
        task_id: str | None,
        command: str,
        workdir: str | None = None,
        timeout_seconds: float = 300.0,
    ) -> PendingApproval:
        """Create an approval request for a shell command."""
        approval_id = str(uuid.uuid4())

        approval = PendingApproval(
            id=approval_id,
            action_type="shell",
            session_id=session_id,
            agent_id=agent_id,
            task_id=task_id,
            command=command,
            workdir=workdir,
            expires_at=datetime.utcnow() + timedelta(seconds=timeout_seconds),
        )

        self._pending[approval_id] = approval
        self._approval_events[approval_id] = asyncio.Event()

        logger.info(
            f"Created shell approval request {approval_id} for: {command[:50]}..."
        )

        for callback in self._on_approval_requested:
            try:
                await callback(approval)
            except Exception as e:
                logger.error(f"Error in approval callback: {e}")

        return approval

    def approve(
        self,
        approval_id: str,
        approved_by: str = "user",
        note: str | None = None,
    ) -> bool:
        """Approve a pending request."""
        approval = self._pending.get(approval_id)
        if not approval:
            logger.warning(f"Approval {approval_id} not found")
            return False

        if approval.status != ApprovalStatus.PENDING:
            logger.warning(f"Approval {approval_id} is not pending: {approval.status}")
            return False

        approval.status = ApprovalStatus.APPROVED
        approval.approved_by = approved_by
        approval.approval_note = note

        # Signal waiting tasks
        event = self._approval_events.get(approval_id)
        if event:
            event.set()

        logger.info(f"Approved {approval_id} by {approved_by}")
        return True

    def reject(
        self,
        approval_id: str,
        rejected_by: str = "user",
        reason: str | None = None,
    ) -> bool:
        """Reject a pending request."""
        approval = self._pending.get(approval_id)
        if not approval:
            return False

        if approval.status != ApprovalStatus.PENDING:
            return False

        approval.status = ApprovalStatus.REJECTED
        approval.approved_by = rejected_by
        approval.approval_note = reason

        # Signal waiting tasks
        event = self._approval_events.get(approval_id)
        if event:
            event.set()

        logger.info(f"Rejected {approval_id} by {rejected_by}: {reason}")
        return True

    async def wait_for_approval(
        self,
        approval_id: str,
        timeout: float | None = None,
    ) -> ApprovalStatus:
        """Wait for an approval decision.

        Args:
            approval_id: The approval request ID
            timeout: Timeout in seconds (None = use approval's expires_at)

        Returns:
            The final approval status

        Raises:
            asyncio.TimeoutError: If timeout is exceeded
        """
        approval = self._pending.get(approval_id)
        if not approval:
            raise ValueError(f"Approval {approval_id} not found")

        event = self._approval_events.get(approval_id)
        if not event:
            raise ValueError(f"No event for approval {approval_id}")

        # Calculate timeout
        if timeout is None and approval.expires_at:
            remaining = (approval.expires_at - datetime.utcnow()).total_seconds()
            timeout = max(0, remaining)

        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            approval.status = ApprovalStatus.EXPIRED
            raise

        return approval.status

    def get_pending(self, session_id: str | None = None) -> list[PendingApproval]:
        """Get pending approval requests."""
        approvals = list(self._pending.values())

        if session_id:
            approvals = [a for a in approvals if a.session_id == session_id]

        return [a for a in approvals if a.status == ApprovalStatus.PENDING]

    def get_approval(self, approval_id: str) -> PendingApproval | None:
        """Get an approval by ID."""
        return self._pending.get(approval_id)

    def cleanup_expired(self) -> int:
        """Clean up expired approvals. Returns count of cleaned up."""
        now = datetime.utcnow()
        expired = [
            aid for aid, approval in self._pending.items()
            if approval.expires_at and approval.expires_at < now
            and approval.status == ApprovalStatus.PENDING
        ]

        for aid in expired:
            approval = self._pending[aid]
            approval.status = ApprovalStatus.EXPIRED
            event = self._approval_events.get(aid)
            if event:
                event.set()

        return len(expired)

    def _generate_diff(
        self,
        file_path: str,
        original: str,
        new: str,
    ) -> str:
        """Generate a unified diff."""
        original_lines = original.splitlines(keepends=True)
        new_lines = new.splitlines(keepends=True)

        diff_lines = difflib.unified_diff(
            original_lines,
            new_lines,
            fromfile=f"a/{file_path}",
            tofile=f"b/{file_path}",
        )

        return "".join(diff_lines)


# Global manager instance
diff_approval_manager = DiffApprovalManager()
