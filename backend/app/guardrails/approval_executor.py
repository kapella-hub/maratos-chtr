"""Executor for approved actions.

After an approval is granted, this module safely applies the exact
action that was approved (file write, delete, shell command).

Security guarantees:
1. Only applies actions that have APPROVED status
2. Verifies content hash matches (for writes)
3. Audits all applied actions
4. Handles failures gracefully
"""

import asyncio
import hashlib
import logging
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from app.guardrails.diff_approval import (
    diff_approval_manager,
    PendingApproval,
    ApprovalStatus,
)
from app.guardrails.audit_repository import AuditRepository
from app.tools.base import ToolResult

logger = logging.getLogger(__name__)


class ApprovalExecutionError(Exception):
    """Error during approval execution."""

    def __init__(self, message: str, approval_id: str, recoverable: bool = False):
        super().__init__(message)
        self.approval_id = approval_id
        self.recoverable = recoverable


class ApprovalExecutor:
    """Executes approved actions safely.

    Usage:
        executor = ApprovalExecutor()

        # Execute an approved action
        result = await executor.execute_approved_action(approval_id)
        if result.success:
            print("Action applied successfully")
    """

    async def execute_approved_action(
        self,
        approval_id: str,
        verify_hash: bool = True,
    ) -> ToolResult:
        """Execute an approved action.

        Args:
            approval_id: The approval ID to execute
            verify_hash: Whether to verify content hash for writes

        Returns:
            ToolResult with success/failure status

        Raises:
            ApprovalExecutionError: If execution fails
        """
        approval = diff_approval_manager.get_approval(approval_id)
        if not approval:
            raise ApprovalExecutionError(
                f"Approval {approval_id} not found",
                approval_id,
                recoverable=False,
            )

        if approval.status != ApprovalStatus.APPROVED:
            raise ApprovalExecutionError(
                f"Approval {approval_id} is not approved (status: {approval.status.value})",
                approval_id,
                recoverable=False,
            )

        # Route to appropriate handler
        if approval.action_type == "write":
            return await self._execute_write(approval, verify_hash)
        elif approval.action_type == "delete":
            return await self._execute_delete(approval)
        elif approval.action_type == "shell":
            return await self._execute_shell(approval)
        else:
            raise ApprovalExecutionError(
                f"Unknown action type: {approval.action_type}",
                approval_id,
                recoverable=False,
            )

    async def _execute_write(
        self,
        approval: PendingApproval,
        verify_hash: bool,
    ) -> ToolResult:
        """Execute an approved file write."""
        if not approval.file_path:
            return ToolResult(
                success=False,
                output="",
                error="No file path in approval",
            )

        if approval.new_content is None:
            return ToolResult(
                success=False,
                output="",
                error="No content in approval",
            )

        # Verify hash if requested
        if verify_hash and approval.content_hash:
            actual_hash = hashlib.sha256(approval.new_content.encode()).hexdigest()[:16]
            if actual_hash != approval.content_hash:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Content hash mismatch: expected {approval.content_hash}, got {actual_hash}",
                )

        try:
            # Expand path
            file_path = Path(approval.file_path).expanduser()

            # Create parent directories if needed
            file_path.parent.mkdir(parents=True, exist_ok=True)

            # Write the file
            file_path.write_text(approval.new_content)

            logger.info(f"Applied approved write to {file_path}")

            # Audit the action
            try:
                await AuditRepository.log_file_operation(
                    file_path=str(file_path),
                    operation="write",
                    success=True,
                    approval_id=approval.id,
                    session_id=approval.session_id,
                    task_id=approval.task_id,
                    agent_id=approval.agent_id,
                    in_workspace=True,  # Must be in workspace if approved
                )
            except Exception as e:
                logger.warning(f"Audit logging failed: {e}")

            return ToolResult(
                success=True,
                output=f"File written: {file_path} ({len(approval.new_content)} bytes)",
            )

        except PermissionError as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Permission denied: {e}",
            )
        except Exception as e:
            logger.error(f"Write execution failed: {e}", exc_info=True)
            return ToolResult(
                success=False,
                output="",
                error=str(e),
            )

    async def _execute_delete(self, approval: PendingApproval) -> ToolResult:
        """Execute an approved file delete."""
        if not approval.file_path:
            return ToolResult(
                success=False,
                output="",
                error="No file path in approval",
            )

        try:
            file_path = Path(approval.file_path).expanduser()

            if not file_path.exists():
                return ToolResult(
                    success=True,
                    output=f"File already deleted: {file_path}",
                )

            # Delete the file
            if file_path.is_dir():
                import shutil
                shutil.rmtree(file_path)
            else:
                file_path.unlink()

            logger.info(f"Applied approved delete: {file_path}")

            # Audit the action
            try:
                await AuditRepository.log_file_operation(
                    file_path=str(file_path),
                    operation="delete",
                    success=True,
                    approval_id=approval.id,
                    session_id=approval.session_id,
                    task_id=approval.task_id,
                    agent_id=approval.agent_id,
                    in_workspace=True,
                )
            except Exception as e:
                logger.warning(f"Audit logging failed: {e}")

            return ToolResult(
                success=True,
                output=f"File deleted: {file_path}",
            )

        except PermissionError as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Permission denied: {e}",
            )
        except Exception as e:
            logger.error(f"Delete execution failed: {e}", exc_info=True)
            return ToolResult(
                success=False,
                output="",
                error=str(e),
            )

    async def _execute_shell(self, approval: PendingApproval) -> ToolResult:
        """Execute an approved shell command."""
        if not approval.command:
            return ToolResult(
                success=False,
                output="",
                error="No command in approval",
            )

        try:
            # Run the command
            process = await asyncio.create_subprocess_shell(
                approval.command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=approval.workdir,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=300.0,  # 5 minute timeout
            )

            output = stdout.decode("utf-8", errors="replace")
            error_output = stderr.decode("utf-8", errors="replace")

            success = process.returncode == 0

            logger.info(f"Applied approved shell command: {approval.command[:50]}...")

            # Audit the action
            try:
                await AuditRepository.log_tool_call(
                    tool_name="shell",
                    tool_action="execute",
                    parameters={"command": approval.command, "workdir": approval.workdir},
                    session_id=approval.session_id,
                    task_id=approval.task_id,
                    agent_id=approval.agent_id,
                    requires_approval=True,
                    approval_id=approval.id,
                )
            except Exception as e:
                logger.warning(f"Audit logging failed: {e}")

            if success:
                return ToolResult(
                    success=True,
                    output=output + error_output,
                )
            else:
                return ToolResult(
                    success=False,
                    output=output,
                    error=error_output or f"Command failed with exit code {process.returncode}",
                )

        except asyncio.TimeoutError:
            return ToolResult(
                success=False,
                output="",
                error="Command timed out after 300 seconds",
            )
        except Exception as e:
            logger.error(f"Shell execution failed: {e}", exc_info=True)
            return ToolResult(
                success=False,
                output="",
                error=str(e),
            )


# Global executor instance
approval_executor = ApprovalExecutor()


async def execute_with_approval(
    approval: PendingApproval,
    timeout_seconds: float = 300.0,
) -> ToolResult:
    """Wait for approval and execute the action.

    This is a convenience function that:
    1. Waits for approval (with timeout)
    2. Executes the approved action
    3. Returns the result

    Args:
        approval: The pending approval to wait for
        timeout_seconds: How long to wait for approval

    Returns:
        ToolResult from executing the action
    """
    try:
        # Wait for approval
        status = await diff_approval_manager.wait_for_approval(
            approval.id,
            timeout=timeout_seconds,
        )

        if status == ApprovalStatus.APPROVED:
            # Execute the approved action
            return await approval_executor.execute_approved_action(approval.id)
        elif status == ApprovalStatus.REJECTED:
            return ToolResult(
                success=False,
                output="",
                error=f"Action rejected: {approval.approval_note or 'No reason given'}",
            )
        else:
            return ToolResult(
                success=False,
                output="",
                error=f"Approval not granted (status: {status.value})",
            )

    except asyncio.TimeoutError:
        return ToolResult(
            success=False,
            output="",
            error=f"Approval request timed out after {timeout_seconds}s",
        )
    except Exception as e:
        logger.error(f"Execution with approval failed: {e}", exc_info=True)
        return ToolResult(
            success=False,
            output="",
            error=str(e),
        )
