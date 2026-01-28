"""Tests for the end-to-end diff-first approval workflow.

Tests verify:
1. Approval is created when high-impact action attempted
2. Action is NOT applied before approval
3. Action IS applied after approval and audited
"""

import asyncio
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.guardrails.diff_approval import (
    DiffApprovalManager,
    ApprovalStatus,
    PendingApproval,
    diff_approval_manager,
)
from app.guardrails.approval_executor import (
    ApprovalExecutor,
    ApprovalExecutionError,
    execute_with_approval,
)
from app.guardrails.policies import (
    AgentPolicy,
    BudgetPolicy,
    DiffApprovalPolicy,
    FilesystemPolicy,
)


class TestDiffApprovalManager:
    """Test the DiffApprovalManager class."""

    @pytest.fixture
    def manager(self):
        """Create a fresh manager for each test."""
        return DiffApprovalManager()

    @pytest.mark.asyncio
    async def test_create_write_approval_generates_diff(self, manager):
        """Test that write approval creates a diff."""
        original = "line 1\nline 2\nline 3"
        new = "line 1\nmodified line 2\nline 3\nline 4"

        approval = await manager.create_write_approval(
            session_id="test-session",
            agent_id="coder",
            task_id="task-123",
            file_path="/tmp/test.txt",
            original_content=original,
            new_content=new,
        )

        assert approval.id is not None
        assert approval.action_type == "write"
        assert approval.status == ApprovalStatus.PENDING
        assert approval.diff is not None
        assert "+modified line 2" in approval.diff
        assert "+line 4" in approval.diff
        assert approval.content_hash is not None

    @pytest.mark.asyncio
    async def test_create_shell_approval(self, manager):
        """Test creating shell command approval."""
        approval = await manager.create_shell_approval(
            session_id="test-session",
            agent_id="devops",
            task_id=None,
            command="rm -rf /important",
            workdir="/home/user",
        )

        assert approval.action_type == "shell"
        assert approval.command == "rm -rf /important"
        assert approval.workdir == "/home/user"
        assert approval.status == ApprovalStatus.PENDING

    @pytest.mark.asyncio
    async def test_create_delete_approval(self, manager):
        """Test creating file delete approval."""
        approval = await manager.create_delete_approval(
            session_id="test-session",
            agent_id="coder",
            task_id=None,
            file_path="/tmp/important.txt",
            original_content="important data",
        )

        assert approval.action_type == "delete"
        assert approval.file_path == "/tmp/important.txt"
        assert approval.status == ApprovalStatus.PENDING

    @pytest.mark.asyncio
    async def test_approve_sets_status(self, manager):
        """Test that approving changes status."""
        approval = await manager.create_write_approval(
            session_id="test-session",
            agent_id="coder",
            task_id=None,
            file_path="/tmp/test.txt",
            original_content="",
            new_content="new content",
        )

        result = manager.approve(approval.id, approved_by="admin", note="Looks good")

        assert result is True
        assert approval.status == ApprovalStatus.APPROVED
        assert approval.approved_by == "admin"
        assert approval.approval_note == "Looks good"

    @pytest.mark.asyncio
    async def test_reject_sets_status(self, manager):
        """Test that rejecting changes status."""
        approval = await manager.create_write_approval(
            session_id="test-session",
            agent_id="coder",
            task_id=None,
            file_path="/tmp/test.txt",
            original_content="",
            new_content="new content",
        )

        result = manager.reject(approval.id, rejected_by="admin", reason="Too risky")

        assert result is True
        assert approval.status == ApprovalStatus.REJECTED
        assert approval.approval_note == "Too risky"

    @pytest.mark.asyncio
    async def test_wait_for_approval_returns_on_approve(self, manager):
        """Test waiting for approval."""
        approval = await manager.create_write_approval(
            session_id="test-session",
            agent_id="coder",
            task_id=None,
            file_path="/tmp/test.txt",
            original_content="",
            new_content="content",
        )

        # Approve in background
        async def approve_later():
            await asyncio.sleep(0.1)
            manager.approve(approval.id)

        asyncio.create_task(approve_later())

        status = await manager.wait_for_approval(approval.id, timeout=5.0)
        assert status == ApprovalStatus.APPROVED

    @pytest.mark.asyncio
    async def test_wait_for_approval_timeout(self, manager):
        """Test that wait times out."""
        approval = await manager.create_write_approval(
            session_id="test-session",
            agent_id="coder",
            task_id=None,
            file_path="/tmp/test.txt",
            original_content="",
            new_content="content",
            timeout_seconds=0.1,
        )

        with pytest.raises(asyncio.TimeoutError):
            await manager.wait_for_approval(approval.id, timeout=0.05)

        assert approval.status == ApprovalStatus.EXPIRED

    @pytest.mark.asyncio
    async def test_get_pending_filters_by_session(self, manager):
        """Test filtering pending approvals by session."""
        await manager.create_write_approval(
            session_id="session-1",
            agent_id="coder",
            task_id=None,
            file_path="/tmp/file1.txt",
            original_content="",
            new_content="content1",
        )
        await manager.create_write_approval(
            session_id="session-2",
            agent_id="coder",
            task_id=None,
            file_path="/tmp/file2.txt",
            original_content="",
            new_content="content2",
        )

        session1_pending = manager.get_pending(session_id="session-1")
        all_pending = manager.get_pending()

        assert len(session1_pending) == 1
        assert len(all_pending) == 2

    @pytest.mark.asyncio
    async def test_callback_called_on_approval_created(self, manager):
        """Test that callbacks are called when approval is created."""
        callback_received = []

        async def callback(approval: PendingApproval):
            callback_received.append(approval)

        manager.register_approval_callback(callback)

        await manager.create_write_approval(
            session_id="test",
            agent_id="coder",
            task_id=None,
            file_path="/tmp/test.txt",
            original_content="",
            new_content="content",
        )

        assert len(callback_received) == 1
        assert callback_received[0].action_type == "write"


class TestApprovalExecutor:
    """Test the ApprovalExecutor class."""

    @pytest.fixture
    def executor(self):
        return ApprovalExecutor()

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for file tests."""
        with tempfile.TemporaryDirectory() as td:
            yield td

    @pytest.mark.asyncio
    async def test_execute_write_creates_file(self, executor, temp_dir):
        """Test that approved write creates the file."""
        manager = DiffApprovalManager()
        file_path = os.path.join(temp_dir, "new_file.txt")
        content = "Hello, World!"

        approval = await manager.create_write_approval(
            session_id="test",
            agent_id="coder",
            task_id=None,
            file_path=file_path,
            original_content=None,
            new_content=content,
        )

        # Approve it
        manager.approve(approval.id)

        # Patch the manager
        with patch(
            "app.guardrails.approval_executor.diff_approval_manager", manager
        ), patch(
            "app.guardrails.approval_executor.AuditRepository"
        ) as mock_audit:
            mock_audit.log_file_operation = AsyncMock()
            result = await executor.execute_approved_action(approval.id)

        assert result.success is True
        assert Path(file_path).exists()
        assert Path(file_path).read_text() == content

    @pytest.mark.asyncio
    async def test_execute_not_approved_fails(self, executor):
        """Test that non-approved action fails."""
        manager = DiffApprovalManager()

        approval = await manager.create_write_approval(
            session_id="test",
            agent_id="coder",
            task_id=None,
            file_path="/tmp/test.txt",
            original_content=None,
            new_content="content",
        )

        # Don't approve - leave as pending

        with patch(
            "app.guardrails.approval_executor.diff_approval_manager", manager
        ):
            with pytest.raises(ApprovalExecutionError) as exc_info:
                await executor.execute_approved_action(approval.id)

        assert "not approved" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_execute_delete_removes_file(self, executor, temp_dir):
        """Test that approved delete removes the file."""
        manager = DiffApprovalManager()
        file_path = os.path.join(temp_dir, "to_delete.txt")

        # Create the file first
        Path(file_path).write_text("content to delete")
        assert Path(file_path).exists()

        approval = await manager.create_delete_approval(
            session_id="test",
            agent_id="coder",
            task_id=None,
            file_path=file_path,
        )

        manager.approve(approval.id)

        with patch(
            "app.guardrails.approval_executor.diff_approval_manager", manager
        ), patch(
            "app.guardrails.approval_executor.AuditRepository"
        ) as mock_audit:
            mock_audit.log_file_operation = AsyncMock()
            result = await executor.execute_approved_action(approval.id)

        assert result.success is True
        assert not Path(file_path).exists()

    @pytest.mark.asyncio
    async def test_execute_shell_runs_command(self, executor, temp_dir):
        """Test that approved shell command runs."""
        manager = DiffApprovalManager()
        output_file = os.path.join(temp_dir, "output.txt")

        approval = await manager.create_shell_approval(
            session_id="test",
            agent_id="devops",
            task_id=None,
            command=f"echo 'hello' > {output_file}",
            workdir=temp_dir,
        )

        manager.approve(approval.id)

        with patch(
            "app.guardrails.approval_executor.diff_approval_manager", manager
        ), patch(
            "app.guardrails.approval_executor.AuditRepository"
        ) as mock_audit:
            mock_audit.log_tool_call = AsyncMock()
            result = await executor.execute_approved_action(approval.id)

        assert result.success is True
        assert Path(output_file).exists()

    @pytest.mark.asyncio
    async def test_hash_verification_fails_on_mismatch(self, executor, temp_dir):
        """Test that hash verification catches tampering."""
        manager = DiffApprovalManager()
        file_path = os.path.join(temp_dir, "test.txt")

        approval = await manager.create_write_approval(
            session_id="test",
            agent_id="coder",
            task_id=None,
            file_path=file_path,
            original_content=None,
            new_content="original content",
        )

        # Tamper with the content after approval creation
        approval.new_content = "tampered content"

        manager.approve(approval.id)

        with patch(
            "app.guardrails.approval_executor.diff_approval_manager", manager
        ):
            result = await executor.execute_approved_action(
                approval.id, verify_hash=True
            )

        assert result.success is False
        assert "hash mismatch" in result.error.lower()


class TestExecuteWithApproval:
    """Test the execute_with_approval convenience function."""

    @pytest.mark.asyncio
    async def test_waits_and_executes_on_approve(self):
        """Test that it waits for approval then executes."""
        manager = DiffApprovalManager()

        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = os.path.join(temp_dir, "test.txt")

            approval = await manager.create_write_approval(
                session_id="test",
                agent_id="coder",
                task_id=None,
                file_path=file_path,
                original_content=None,
                new_content="test content",
            )

            # Approve after a short delay
            async def approve_later():
                await asyncio.sleep(0.1)
                manager.approve(approval.id)

            asyncio.create_task(approve_later())

            with patch(
                "app.guardrails.approval_executor.diff_approval_manager", manager
            ), patch(
                "app.guardrails.approval_executor.AuditRepository"
            ) as mock_audit:
                mock_audit.log_file_operation = AsyncMock()
                result = await execute_with_approval(
                    approval, timeout_seconds=5.0
                )

            assert result.success is True
            assert Path(file_path).exists()

    @pytest.mark.asyncio
    async def test_returns_error_on_reject(self):
        """Test that rejection returns error result."""
        manager = DiffApprovalManager()

        approval = await manager.create_write_approval(
            session_id="test",
            agent_id="coder",
            task_id=None,
            file_path="/tmp/test.txt",
            original_content=None,
            new_content="content",
        )

        # Reject after a short delay
        async def reject_later():
            await asyncio.sleep(0.1)
            manager.reject(approval.id, reason="Not allowed")

        asyncio.create_task(reject_later())

        with patch(
            "app.guardrails.approval_executor.diff_approval_manager", manager
        ):
            result = await execute_with_approval(
                approval, timeout_seconds=5.0
            )

        assert result.success is False
        assert "rejected" in result.error.lower()


class TestApprovalIntegration:
    """Integration tests for the full approval workflow."""

    @pytest.mark.asyncio
    async def test_file_not_created_before_approval(self):
        """Verify file is NOT created before approval granted."""
        manager = DiffApprovalManager()

        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = os.path.join(temp_dir, "guarded_file.txt")

            # Create approval request
            approval = await manager.create_write_approval(
                session_id="test",
                agent_id="coder",
                task_id=None,
                file_path=file_path,
                original_content=None,
                new_content="secret data",
            )

            # File should NOT exist yet
            assert not Path(file_path).exists(), "File created before approval!"

            # Approve and execute
            manager.approve(approval.id)

            executor = ApprovalExecutor()
            with patch(
                "app.guardrails.approval_executor.diff_approval_manager", manager
            ), patch(
                "app.guardrails.approval_executor.AuditRepository"
            ) as mock_audit:
                mock_audit.log_file_operation = AsyncMock()
                result = await executor.execute_approved_action(approval.id)

            # Now file should exist
            assert result.success
            assert Path(file_path).exists(), "File not created after approval!"
            assert Path(file_path).read_text() == "secret data"

    @pytest.mark.asyncio
    async def test_audit_logged_after_execution(self):
        """Verify audit entry created after successful execution."""
        manager = DiffApprovalManager()

        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = os.path.join(temp_dir, "audited_file.txt")

            approval = await manager.create_write_approval(
                session_id="audit-session",
                agent_id="coder",
                task_id="task-456",
                file_path=file_path,
                original_content=None,
                new_content="audited content",
            )

            manager.approve(approval.id)

            executor = ApprovalExecutor()
            with patch(
                "app.guardrails.approval_executor.diff_approval_manager", manager
            ), patch(
                "app.guardrails.approval_executor.AuditRepository"
            ) as mock_audit:
                mock_audit.log_file_operation = AsyncMock()
                await executor.execute_approved_action(approval.id)

                # Verify audit was called with correct parameters
                mock_audit.log_file_operation.assert_called_once()
                call_kwargs = mock_audit.log_file_operation.call_args.kwargs
                assert call_kwargs["file_path"] == file_path
                assert call_kwargs["operation"] == "write"
                assert call_kwargs["success"] is True
                assert call_kwargs["approval_id"] == approval.id
                assert call_kwargs["session_id"] == "audit-session"
                assert call_kwargs["agent_id"] == "coder"

    @pytest.mark.asyncio
    async def test_shell_not_run_before_approval(self):
        """Verify shell command is NOT run before approval."""
        manager = DiffApprovalManager()

        with tempfile.TemporaryDirectory() as temp_dir:
            marker_file = os.path.join(temp_dir, "shell_ran.marker")

            # Create approval for command that creates a marker file
            approval = await manager.create_shell_approval(
                session_id="test",
                agent_id="devops",
                task_id=None,
                command=f"touch {marker_file}",
                workdir=temp_dir,
            )

            # Marker should NOT exist
            assert not Path(marker_file).exists(), "Command ran before approval!"

            # Approve and execute
            manager.approve(approval.id)

            executor = ApprovalExecutor()
            with patch(
                "app.guardrails.approval_executor.diff_approval_manager", manager
            ), patch(
                "app.guardrails.approval_executor.AuditRepository"
            ) as mock_audit:
                mock_audit.log_tool_call = AsyncMock()
                result = await executor.execute_approved_action(approval.id)

            # Now marker should exist
            assert result.success
            assert Path(marker_file).exists(), "Command not run after approval!"
