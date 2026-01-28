"""Unified guardrails enforcer for all tool execution paths.

This module provides a single, consistent enforcement point that MUST be called
before any tool execution, regardless of the entry point:

- Chat API → interpreter → enforcer → tool
- Skills API → executor → enforcer → tool
- Direct tool calls → enforcer → tool
- Subagent execution → agent → enforcer → tool

Usage:
    enforcer = GuardrailsEnforcer.for_agent("coder", session_id="...")

    # Check before execution
    allowed, error = await enforcer.check_tool_execution("filesystem", {"action": "write", "path": "/etc/passwd"})
    if not allowed:
        return ToolResult(success=False, output="", error=error)

    # Execute tool
    result = await tool.execute(**args)

    # Record after execution
    await enforcer.record_tool_execution("filesystem", args, result)
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.guardrails.policies import AgentPolicy, get_agent_policy, AGENT_POLICIES
from app.guardrails.budgets import BudgetTracker, BudgetExceededError, BudgetType
from app.guardrails.diff_approval import diff_approval_manager, ApprovalStatus
from app.guardrails.audit_repository import AuditRepository
from app.tools.base import ToolResult

logger = logging.getLogger(__name__)


# Default restrictive policy for unknown/unspecified agents
_DEFAULT_RESTRICTIVE_POLICY = AgentPolicy(
    agent_id="__default__",
    description="Default restrictive policy for unspecified agents",
    allowed_tools=["filesystem"],  # Only read-only filesystem by default
    # Use default FilesystemPolicy which is read-only
)


@dataclass
class EnforcementResult:
    """Result of a guardrails check."""

    allowed: bool
    error: str | None = None
    requires_approval: bool = False
    approval_id: str | None = None
    audit_log_id: str | None = None

    # Violation flags for audit
    policy_blocked: bool = False
    sandbox_violation: bool = False
    budget_exceeded: bool = False


@dataclass
class EnforcementContext:
    """Context for guardrails enforcement."""

    session_id: str | None = None
    task_id: str | None = None
    agent_id: str | None = None
    agent_policy: AgentPolicy | None = None
    budget_tracker: BudgetTracker | None = None

    # Feature flags
    enable_audit: bool = True
    enable_budget: bool = True
    enable_diff_approval: bool = False

    # Execution tracking
    tool_calls_in_session: int = 0
    files_written: list[str] = field(default_factory=list)


class GuardrailsEnforcer:
    """Unified guardrails enforcer for all tool execution paths.

    This class centralizes all security enforcement:
    - Tool allowlists per agent
    - Filesystem write jail (workspace-only)
    - Budget limits (tool calls, shell time, spawns)
    - Diff-first approval for high-impact actions
    - Audit logging for all operations

    IMPORTANT: This enforcer MUST be used before every tool execution,
    regardless of the entry point.
    """

    def __init__(self, context: EnforcementContext):
        self.context = context
        self._pending_approval_id: str | None = None

    @classmethod
    def for_agent(
        cls,
        agent_id: str,
        session_id: str | None = None,
        task_id: str | None = None,
        enable_audit: bool = True,
        enable_diff_approval: bool | None = None,
    ) -> "GuardrailsEnforcer":
        """Create an enforcer with guardrails for a specific agent.

        This is the recommended factory method.

        Args:
            agent_id: The agent ID (mo, coder, reviewer, etc.)
            session_id: Session ID for tracking
            task_id: Task ID for tracking
            enable_audit: Whether to log to audit repository
            enable_diff_approval: Override diff approval (None = use agent policy)
        """
        policy = get_agent_policy(agent_id)

        # Create budget tracker from policy
        budget_tracker = BudgetTracker(
            policy=policy.budget,
            session_id=session_id,
            agent_id=agent_id,
        )

        # Determine diff approval setting
        if enable_diff_approval is None:
            enable_diff_approval = policy.diff_approval.enabled

        context = EnforcementContext(
            session_id=session_id,
            task_id=task_id,
            agent_id=agent_id,
            agent_policy=policy,
            budget_tracker=budget_tracker,
            enable_audit=enable_audit,
            enable_budget=True,
            enable_diff_approval=enable_diff_approval,
        )

        return cls(context)

    @classmethod
    def for_skill(
        cls,
        skill_id: str,
        session_id: str | None = None,
        task_id: str | None = None,
        workdir: str | None = None,
    ) -> "GuardrailsEnforcer":
        """Create an enforcer for skill execution.

        Skills use a restricted policy that only allows kiro, shell, filesystem.
        """
        # Skills run with coder-like permissions but restricted tools
        policy = get_agent_policy("coder")

        # Override to restrict tools for skills
        from app.guardrails.policies import AgentPolicy, FilesystemPolicy, BudgetPolicy
        skill_policy = AgentPolicy(
            agent_id=f"skill:{skill_id}",
            description=f"Skill execution policy for {skill_id}",
            allowed_tools=["kiro", "shell", "filesystem"],
            filesystem=FilesystemPolicy(
                read_paths=["*"],
                write_paths=[workdir] if workdir else ["~/maratos-workspace"],
                write_allowed=True,
                workspace_only=True,
                workspace_path=workdir or "~/maratos-workspace",
            ),
            budget=BudgetPolicy(
                max_tool_loops_per_message=10,
                max_tool_calls_per_message=30,
                max_shell_time_seconds=300.0,
            ),
        )

        budget_tracker = BudgetTracker(
            policy=skill_policy.budget,
            session_id=session_id,
            agent_id=f"skill:{skill_id}",
        )

        context = EnforcementContext(
            session_id=session_id,
            task_id=task_id,
            agent_id=f"skill:{skill_id}",
            agent_policy=skill_policy,
            budget_tracker=budget_tracker,
            enable_audit=True,
            enable_budget=True,
            enable_diff_approval=False,  # Skills don't use diff approval
        )

        return cls(context)

    @classmethod
    def default(
        cls,
        session_id: str | None = None,
    ) -> "GuardrailsEnforcer":
        """Create a default restrictive enforcer.

        Used when no agent is specified. Very restrictive - read-only filesystem only.
        """
        context = EnforcementContext(
            session_id=session_id,
            agent_policy=_DEFAULT_RESTRICTIVE_POLICY,
            budget_tracker=BudgetTracker(
                policy=_DEFAULT_RESTRICTIVE_POLICY.budget,
                session_id=session_id,
            ),
            enable_audit=True,
            enable_budget=True,
            enable_diff_approval=False,
        )
        return cls(context)

    # =========================================================================
    # Main Enforcement Methods
    # =========================================================================

    async def check_tool_execution(
        self,
        tool_id: str,
        args: dict[str, Any],
    ) -> EnforcementResult:
        """Check if a tool execution is allowed.

        This MUST be called before every tool execution.

        Returns:
            EnforcementResult with allowed=True if execution can proceed,
            or allowed=False with error message if blocked.
        """
        policy = self.context.agent_policy or _DEFAULT_RESTRICTIVE_POLICY
        result = EnforcementResult(allowed=True)

        # 1. Check tool allowlist
        if not policy.is_tool_allowed(tool_id):
            result.allowed = False
            result.policy_blocked = True
            result.error = f"Tool '{tool_id}' not allowed for agent '{self.context.agent_id}'"
            await self._log_blocked_tool(tool_id, args, result)
            return result

        # 2. Check budget limits
        if self.context.enable_budget and self.context.budget_tracker:
            try:
                self.context.budget_tracker.check_tool_call()

                # Special check for shell commands
                if tool_id == "shell":
                    self.context.budget_tracker.check_shell_call()

            except BudgetExceededError as e:
                result.allowed = False
                result.budget_exceeded = True
                result.error = e.message
                await self._log_budget_exceeded(tool_id, args, e)
                return result

        # 3. Check filesystem jail for write operations
        if tool_id == "filesystem":
            jail_result = self._check_filesystem_jail(args)
            if not jail_result.allowed:
                await self._log_blocked_tool(tool_id, args, jail_result)
                return jail_result

        # 4. Check diff-first approval for high-impact actions
        if self.context.enable_diff_approval:
            approval_result = await self._check_diff_approval(tool_id, args)
            if not approval_result.allowed:
                return approval_result
            if approval_result.requires_approval:
                result.requires_approval = True
                result.approval_id = approval_result.approval_id

        # 5. Log tool call (before execution)
        if self.context.enable_audit:
            try:
                log = await AuditRepository.log_tool_call(
                    tool_name=tool_id,
                    tool_action=args.get("action"),
                    parameters=args,
                    session_id=self.context.session_id,
                    task_id=self.context.task_id,
                    agent_id=self.context.agent_id,
                )
                result.audit_log_id = log.id
            except Exception as e:
                logger.warning(f"Audit logging failed: {e}")

        return result

    async def record_tool_execution(
        self,
        tool_id: str,
        args: dict[str, Any],
        tool_result: ToolResult,
        duration_ms: float,
        enforcement_result: EnforcementResult | None = None,
    ) -> None:
        """Record a tool execution after it completes.

        This MUST be called after every tool execution.
        """
        # Record in budget tracker
        if self.context.enable_budget and self.context.budget_tracker:
            output_size = len(tool_result.output) if tool_result.output else 0
            self.context.budget_tracker.record_tool_call(output_size=output_size)

            # Record shell time if applicable
            if tool_id == "shell" and tool_result.success:
                self.context.budget_tracker.record_shell_time(duration_ms / 1000)

        # Track written files
        if tool_id == "filesystem" and args.get("action") == "write":
            path = args.get("path", "")
            if path and tool_result.success:
                self.context.files_written.append(path)

        # Log result to audit
        if self.context.enable_audit and enforcement_result and enforcement_result.audit_log_id:
            try:
                await AuditRepository.log_tool_result(
                    log_id=enforcement_result.audit_log_id,
                    success=tool_result.success,
                    output=tool_result.output,
                    error=tool_result.error,
                    duration_ms=duration_ms,
                    sandbox_violation=enforcement_result.sandbox_violation,
                    budget_exceeded=enforcement_result.budget_exceeded,
                    policy_blocked=enforcement_result.policy_blocked,
                )
            except Exception as e:
                logger.warning(f"Audit result logging failed: {e}")

        # Log file operation if applicable
        if tool_id == "filesystem" and self.context.enable_audit:
            action = args.get("action", "")
            if action in ("write", "delete", "copy"):
                try:
                    await AuditRepository.log_file_operation(
                        file_path=args.get("path", ""),
                        operation=action,
                        success=tool_result.success,
                        error=tool_result.error,
                        in_workspace=self._is_in_workspace(args.get("path", "")),
                        session_id=self.context.session_id,
                        task_id=self.context.task_id,
                        agent_id=self.context.agent_id,
                    )
                except Exception as e:
                    logger.warning(f"File operation audit failed: {e}")

        self.context.tool_calls_in_session += 1

    # =========================================================================
    # Filesystem Jail Enforcement
    # =========================================================================

    def _check_filesystem_jail(self, args: dict[str, Any]) -> EnforcementResult:
        """Check filesystem operations against jail policy."""
        policy = self.context.agent_policy or _DEFAULT_RESTRICTIVE_POLICY
        action = args.get("action", "")
        path = args.get("path", "")
        dest = args.get("dest", "")

        result = EnforcementResult(allowed=True)

        # Read operations are always allowed
        if action in ("read", "list", "exists"):
            return result

        # Write/delete/copy operations need jail check
        if action in ("write", "delete", "copy", "create_dir"):
            target_path = dest if action == "copy" else path

            if not target_path:
                result.allowed = False
                result.error = f"Missing path for {action} operation"
                return result

            # Check write permission
            if not policy.filesystem.can_write(target_path):
                result.allowed = False
                result.sandbox_violation = True
                workspace = policy.filesystem.workspace_path
                result.error = f"Write operations only allowed in workspace: {workspace}"
                return result

        return result

    def _is_in_workspace(self, path: str) -> bool:
        """Check if path is within the workspace."""
        if not path:
            return False

        policy = self.context.agent_policy or _DEFAULT_RESTRICTIVE_POLICY
        workspace = policy.filesystem.workspace_path

        try:
            expanded_path = Path(path).expanduser().resolve()
            workspace_expanded = Path(workspace).expanduser().resolve()
            expanded_path.relative_to(workspace_expanded)
            return True
        except ValueError:
            return False

    # =========================================================================
    # Diff-First Approval
    # =========================================================================

    async def _check_diff_approval(
        self,
        tool_id: str,
        args: dict[str, Any],
    ) -> EnforcementResult:
        """Check if diff-first approval is required."""
        policy = self.context.agent_policy
        if not policy or not policy.diff_approval.enabled:
            return EnforcementResult(allowed=True)

        diff_policy = policy.diff_approval
        result = EnforcementResult(allowed=True)

        # Check filesystem operations
        if tool_id == "filesystem":
            action = args.get("action", "")
            file_path = args.get("path", "")

            if action == "write" and diff_policy.require_approval_for_writes:
                if diff_policy.requires_approval("write", file_path):
                    result.requires_approval = True

            elif action == "delete" and diff_policy.require_approval_for_deletes:
                result.requires_approval = True

        # Check shell operations
        elif tool_id == "shell" and diff_policy.require_approval_for_shell:
            result.requires_approval = True

        # If approval required, create approval request and wait
        if result.requires_approval:
            try:
                approval = await self._create_approval_request(tool_id, args)
                result.approval_id = approval.id

                # Wait for approval
                status = await diff_approval_manager.wait_for_approval(
                    approval.id,
                    timeout=diff_policy.approval_timeout_seconds,
                )

                if status == ApprovalStatus.REJECTED:
                    result.allowed = False
                    result.error = f"Action rejected: {approval.approval_note or 'No reason given'}"
                elif status == ApprovalStatus.EXPIRED:
                    result.allowed = False
                    result.error = "Approval request expired"
                # APPROVED - allow execution

            except asyncio.TimeoutError:
                result.allowed = False
                result.error = "Approval request timed out"

        return result

    async def _create_approval_request(
        self,
        tool_id: str,
        args: dict[str, Any],
    ):
        """Create an approval request for a high-impact action."""
        if tool_id == "filesystem":
            action = args.get("action", "")
            file_path = args.get("path", "")

            if action == "write":
                new_content = args.get("content", "")
                original_content = None

                try:
                    path_obj = Path(file_path).expanduser()
                    if path_obj.exists():
                        original_content = path_obj.read_text()
                except Exception:
                    pass

                return await diff_approval_manager.create_write_approval(
                    session_id=self.context.session_id or "",
                    agent_id=self.context.agent_id or "",
                    task_id=self.context.task_id,
                    file_path=file_path,
                    original_content=original_content,
                    new_content=new_content,
                )

            elif action == "delete":
                original_content = None
                try:
                    path_obj = Path(file_path).expanduser()
                    if path_obj.exists() and path_obj.is_file():
                        original_content = path_obj.read_text()
                except Exception:
                    pass

                return await diff_approval_manager.create_delete_approval(
                    session_id=self.context.session_id or "",
                    agent_id=self.context.agent_id or "",
                    task_id=self.context.task_id,
                    file_path=file_path,
                    original_content=original_content,
                )

        elif tool_id == "shell":
            return await diff_approval_manager.create_shell_approval(
                session_id=self.context.session_id or "",
                agent_id=self.context.agent_id or "",
                task_id=self.context.task_id,
                command=args.get("command", ""),
                workdir=args.get("workdir"),
            )

        raise ValueError(f"Cannot create approval for tool: {tool_id}")

    # =========================================================================
    # Audit Logging Helpers
    # =========================================================================

    async def _log_blocked_tool(
        self,
        tool_id: str,
        args: dict[str, Any],
        result: EnforcementResult,
    ) -> None:
        """Log a blocked tool execution."""
        if not self.context.enable_audit:
            return

        try:
            log = await AuditRepository.log_tool_call(
                tool_name=tool_id,
                tool_action=args.get("action"),
                parameters=args,
                session_id=self.context.session_id,
                task_id=self.context.task_id,
                agent_id=self.context.agent_id,
            )
            await AuditRepository.log_tool_result(
                log_id=log.id,
                success=False,
                error=result.error,
                sandbox_violation=result.sandbox_violation,
                budget_exceeded=result.budget_exceeded,
                policy_blocked=result.policy_blocked,
            )
        except Exception as e:
            logger.warning(f"Failed to log blocked tool: {e}")

    async def _log_budget_exceeded(
        self,
        tool_id: str,
        args: dict[str, Any],
        error: BudgetExceededError,
    ) -> None:
        """Log a budget exceeded event."""
        if not self.context.enable_audit:
            return

        try:
            await AuditRepository.log_budget_check(
                budget_type=error.budget_type.value,
                current_value=float(error.current),
                limit_value=float(error.limit),
                exceeded=True,
                session_id=self.context.session_id,
                task_id=self.context.task_id,
                agent_id=self.context.agent_id,
            )
        except Exception as e:
            logger.warning(f"Failed to log budget exceeded: {e}")

    # =========================================================================
    # Utility Methods
    # =========================================================================

    def get_budget_remaining(self) -> dict[str, Any] | None:
        """Get remaining budget."""
        if self.context.budget_tracker:
            return self.context.budget_tracker.get_remaining()
        return None

    def is_budget_exhausted(self) -> bool:
        """Check if any budget is exhausted."""
        if self.context.budget_tracker:
            return self.context.budget_tracker.is_budget_exhausted()
        return False

    def reset_message_counters(self) -> None:
        """Reset per-message counters."""
        if self.context.budget_tracker:
            self.context.budget_tracker.reset_message_counters()

    def get_enforcement_summary(self) -> dict[str, Any]:
        """Get summary of enforcement activity."""
        return {
            "agent_id": self.context.agent_id,
            "session_id": self.context.session_id,
            "tool_calls": self.context.tool_calls_in_session,
            "files_written": self.context.files_written,
            "budget_remaining": self.get_budget_remaining(),
            "budget_exhausted": self.is_budget_exhausted(),
        }
