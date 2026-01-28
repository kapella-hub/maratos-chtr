"""Comprehensive security tests for enterprise guardrails.

Tests cover:
- Filesystem jail enforcement (write outside workspace blocked)
- Tool allowlists (reviewer cannot write)
- Budget enforcement (tool loops, spawned tasks, shell time)
- Audit logging functionality
- Diff-first mode approval flow
"""

import asyncio
import pytest
from pathlib import Path
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

# Guardrails imports
from app.guardrails import (
    AgentPolicy,
    BudgetPolicy,
    FilesystemPolicy,
    DiffApprovalPolicy,
    get_agent_policy,
    AGENT_POLICIES,
    BudgetTracker,
    BudgetExceededError,
    BudgetType,
    DiffApprovalManager,
    PendingApproval,
    ApprovalStatus,
    AuditRepository,
)

# Tool interpreter imports
from app.tools.interpreter import (
    ToolInterpreter,
    InterpreterContext,
    ToolPolicy,
    ToolInvocation,
    execute_invocations,
)
from app.tools.base import ToolResult


# =============================================================================
# Test: Filesystem Jail Enforcement
# =============================================================================

class TestFilesystemJail:
    """Test that writes outside the workspace are blocked."""

    def test_filesystem_policy_can_write_in_workspace(self):
        """Files in workspace should be writable."""
        policy = FilesystemPolicy(
            write_paths=["~/maratos-workspace"],
            write_allowed=True,
            workspace_only=True,
            workspace_path="~/maratos-workspace",
        )

        # Should allow write in workspace
        assert policy.can_write("~/maratos-workspace/test.py")
        assert policy.can_write("~/maratos-workspace/subdir/test.py")

    def test_filesystem_policy_blocks_write_outside_workspace(self):
        """Files outside workspace should not be writable."""
        policy = FilesystemPolicy(
            write_paths=["~/maratos-workspace"],
            write_allowed=True,
            workspace_only=True,
            workspace_path="~/maratos-workspace",
        )

        # Should block write outside workspace
        assert not policy.can_write("/etc/passwd")
        assert not policy.can_write("~/other-project/test.py")
        assert not policy.can_write("/tmp/test.py")

    def test_filesystem_policy_read_anywhere(self):
        """Reading should be allowed anywhere."""
        policy = FilesystemPolicy(
            read_paths=["*"],
            read_allowed=True,
            write_paths=["~/maratos-workspace"],
            write_allowed=True,
        )

        # Should allow read from anywhere
        assert policy.can_read("/etc/passwd")
        assert policy.can_read("~/other-project/test.py")
        assert policy.can_read("~/maratos-workspace/test.py")

    def test_reviewer_has_no_write_access(self):
        """Reviewer agent should have no write paths."""
        reviewer_policy = get_agent_policy("reviewer")

        assert reviewer_policy.filesystem.write_allowed is False
        assert reviewer_policy.filesystem.write_paths == []

        # Should not be able to write anywhere
        assert not reviewer_policy.filesystem.can_write("~/maratos-workspace/test.py")
        assert not reviewer_policy.filesystem.can_write("/any/path")

    @pytest.mark.asyncio
    async def test_interpreter_blocks_write_outside_workspace(self):
        """Interpreter should block write operations outside workspace."""
        context = InterpreterContext(
            session_id="test-session",
            agent_id="coder",
            policy=ToolPolicy(
                allowed_tools=["filesystem"],
                workspace_path="/workspace",
            ),
            enable_audit=False,
        )

        invocation = ToolInvocation(
            tool_id="filesystem",
            args={"action": "write", "path": "/etc/test", "content": "malicious"},
            raw_json="{}",
        )

        # Mock tool registry to avoid actual execution
        with patch("app.tools.interpreter.tool_registry") as mock_registry:
            mock_tool = MagicMock()
            mock_registry.get.return_value = mock_tool

            results = await execute_invocations([invocation], context)

        # Should be blocked
        assert len(results) == 1
        assert results[0].result.success is False
        assert "workspace" in results[0].result.error.lower()


# =============================================================================
# Test: Tool Allowlists per Agent
# =============================================================================

class TestToolAllowlists:
    """Test that tool allowlists are enforced per agent."""

    def test_reviewer_allowed_tools(self):
        """Reviewer should have limited tool access."""
        reviewer = get_agent_policy("reviewer")

        # Reviewer can use these tools
        assert reviewer.is_tool_allowed("filesystem")
        assert reviewer.is_tool_allowed("shell")
        assert reviewer.is_tool_allowed("kiro")

        # But not these (if any are restricted)
        # Note: Current policy allows filesystem, shell, kiro for reviewer

    def test_mo_has_orchestration_tools(self):
        """MO should have access to orchestration tools."""
        mo = get_agent_policy("mo")

        assert mo.is_tool_allowed("routing")
        assert mo.is_tool_allowed("sessions")
        assert mo.is_tool_allowed("canvas")

    def test_coder_cannot_spawn(self):
        """Coder should not be able to spawn subagents."""
        coder = get_agent_policy("coder")

        assert coder.budget.max_spawned_tasks_per_run == 0

    @pytest.mark.asyncio
    async def test_interpreter_blocks_disallowed_tool(self):
        """Interpreter should block tools not in allowlist."""
        context = InterpreterContext(
            session_id="test-session",
            agent_id="test",
            policy=ToolPolicy(
                allowed_tools=["filesystem"],  # Only filesystem allowed
            ),
            enable_audit=False,
        )

        invocation = ToolInvocation(
            tool_id="shell",  # Not in allowlist
            args={"command": "ls"},
            raw_json="{}",
        )

        results = await execute_invocations([invocation], context)

        assert len(results) == 1
        assert results[0].result.success is False
        assert "not allowed" in results[0].result.error.lower()


# =============================================================================
# Test: Budget Enforcement
# =============================================================================

class TestBudgetEnforcement:
    """Test budget limits and enforcement."""

    def test_tool_loop_budget_exceeded(self):
        """Should raise error when tool loops exceeded."""
        policy = BudgetPolicy(max_tool_loops_per_message=3)
        tracker = BudgetTracker(policy)

        # Record 3 loops
        for _ in range(3):
            tracker.check_tool_loop()
            tracker.record_tool_loop()

        # 4th should fail
        with pytest.raises(BudgetExceededError) as exc_info:
            tracker.check_tool_loop()

        assert exc_info.value.budget_type == BudgetType.TOOL_LOOPS
        assert exc_info.value.current == 3
        assert exc_info.value.limit == 3

    def test_tool_call_budget_per_message(self):
        """Should enforce max tool calls per message."""
        policy = BudgetPolicy(max_tool_calls_per_message=5)
        tracker = BudgetTracker(policy)

        # Record 5 calls
        for _ in range(5):
            tracker.check_tool_call()
            tracker.record_tool_call()

        # 6th should fail
        with pytest.raises(BudgetExceededError) as exc_info:
            tracker.check_tool_call()

        assert exc_info.value.budget_type == BudgetType.TOOL_CALLS_MESSAGE

    def test_tool_call_budget_per_session(self):
        """Should enforce max tool calls per session."""
        policy = BudgetPolicy(
            max_tool_calls_per_message=100,
            max_tool_calls_per_session=10,
        )
        tracker = BudgetTracker(policy)

        # Record 10 calls
        for _ in range(10):
            tracker.check_tool_call()
            tracker.record_tool_call()

        # 11th should fail
        with pytest.raises(BudgetExceededError) as exc_info:
            tracker.check_tool_call()

        assert exc_info.value.budget_type == BudgetType.TOOL_CALLS_SESSION

    def test_spawn_budget_exceeded(self):
        """Should raise error when spawn limit exceeded."""
        policy = BudgetPolicy(max_spawned_tasks_per_run=3)
        tracker = BudgetTracker(policy)

        # Record 3 spawns
        for _ in range(3):
            tracker.check_spawn()
            tracker.record_spawn()

        # 4th should fail
        with pytest.raises(BudgetExceededError) as exc_info:
            tracker.check_spawn()

        assert exc_info.value.budget_type == BudgetType.SPAWNED_TASKS

    def test_spawn_depth_exceeded(self):
        """Should raise error when spawn depth exceeded."""
        policy = BudgetPolicy(max_nested_spawn_depth=2)
        tracker = BudgetTracker(policy)

        # Depth 0, 1 should work
        tracker.check_spawn(depth=0)
        tracker.check_spawn(depth=1)

        # Depth 2 should fail (>= max)
        with pytest.raises(BudgetExceededError) as exc_info:
            tracker.check_spawn(depth=2)

        assert exc_info.value.budget_type == BudgetType.SPAWN_DEPTH

    def test_shell_time_budget(self):
        """Should track shell execution time."""
        policy = BudgetPolicy(
            max_shell_time_seconds=10.0,
            max_total_shell_time_per_session=30.0,
        )
        tracker = BudgetTracker(policy)

        # Record some shell time
        tracker.record_shell_time(5.0)
        tracker.record_shell_time(10.0)
        tracker.record_shell_time(15.0)  # Total: 30s

        # Next shell call should fail
        with pytest.raises(BudgetExceededError) as exc_info:
            tracker.check_shell_call()

        assert exc_info.value.budget_type == BudgetType.TOTAL_SHELL_TIME

    def test_message_counter_reset(self):
        """Message counters should reset properly."""
        policy = BudgetPolicy(max_tool_loops_per_message=3)
        tracker = BudgetTracker(policy)

        # Use up the message budget
        for _ in range(3):
            tracker.check_tool_loop()
            tracker.record_tool_loop()

        # Should fail
        with pytest.raises(BudgetExceededError):
            tracker.check_tool_loop()

        # Reset counters
        tracker.reset_message_counters()

        # Should work again
        tracker.check_tool_loop()
        tracker.record_tool_loop()

    def test_budget_summary(self):
        """Should provide accurate budget summary."""
        policy = BudgetPolicy(
            max_tool_loops_per_message=10,
            max_tool_calls_per_message=20,
        )
        tracker = BudgetTracker(policy)

        tracker.record_tool_loop()
        tracker.record_tool_loop()
        tracker.record_tool_call()

        summary = tracker.get_usage_summary()

        assert summary["usage"]["tool_loops"] == 2
        assert summary["usage"]["tool_calls_message"] == 1
        assert summary["remaining"]["tool_loops"] == 8
        assert summary["remaining"]["tool_calls_message"] == 19


# =============================================================================
# Test: Diff-First Mode
# =============================================================================

class TestDiffFirstMode:
    """Test diff-first approval workflow."""

    @pytest.mark.asyncio
    async def test_create_write_approval(self):
        """Should create write approval with diff."""
        manager = DiffApprovalManager()

        approval = await manager.create_write_approval(
            session_id="test-session",
            agent_id="coder",
            task_id="task-1",
            file_path="test.py",
            original_content="print('old')",
            new_content="print('new')",
        )

        assert approval.id is not None
        assert approval.action_type == "write"
        assert approval.status == ApprovalStatus.PENDING
        assert approval.diff is not None
        assert "old" in approval.diff
        assert "new" in approval.diff

    @pytest.mark.asyncio
    async def test_create_delete_approval(self):
        """Should create delete approval."""
        manager = DiffApprovalManager()

        approval = await manager.create_delete_approval(
            session_id="test-session",
            agent_id="coder",
            task_id="task-1",
            file_path="test.py",
            original_content="content to delete",
        )

        assert approval.action_type == "delete"
        assert approval.file_path == "test.py"
        assert approval.original_content == "content to delete"

    @pytest.mark.asyncio
    async def test_create_shell_approval(self):
        """Should create shell approval."""
        manager = DiffApprovalManager()

        approval = await manager.create_shell_approval(
            session_id="test-session",
            agent_id="devops",
            task_id="task-1",
            command="rm -rf /tmp/test",
            workdir="/workspace",
        )

        assert approval.action_type == "shell"
        assert approval.command == "rm -rf /tmp/test"
        assert approval.workdir == "/workspace"

    @pytest.mark.asyncio
    async def test_approve_request(self):
        """Should approve pending request."""
        manager = DiffApprovalManager()

        approval = await manager.create_write_approval(
            session_id="test-session",
            agent_id="coder",
            task_id="task-1",
            file_path="test.py",
            original_content="",
            new_content="new content",
        )

        # Approve it
        result = manager.approve(approval.id, approved_by="admin", note="LGTM")

        assert result is True
        assert approval.status == ApprovalStatus.APPROVED
        assert approval.approved_by == "admin"
        assert approval.approval_note == "LGTM"

    @pytest.mark.asyncio
    async def test_reject_request(self):
        """Should reject pending request."""
        manager = DiffApprovalManager()

        approval = await manager.create_write_approval(
            session_id="test-session",
            agent_id="coder",
            task_id="task-1",
            file_path="test.py",
            original_content="",
            new_content="new content",
        )

        # Reject it
        result = manager.reject(approval.id, rejected_by="admin", reason="Too risky")

        assert result is True
        assert approval.status == ApprovalStatus.REJECTED
        assert approval.approval_note == "Too risky"

    @pytest.mark.asyncio
    async def test_wait_for_approval(self):
        """Should wait for and return approval status."""
        manager = DiffApprovalManager()

        approval = await manager.create_write_approval(
            session_id="test-session",
            agent_id="coder",
            task_id="task-1",
            file_path="test.py",
            original_content="",
            new_content="new content",
        )

        # Approve in background after a short delay
        async def approve_later():
            await asyncio.sleep(0.1)
            manager.approve(approval.id)

        asyncio.create_task(approve_later())

        # Wait for approval
        status = await manager.wait_for_approval(approval.id, timeout=5.0)

        assert status == ApprovalStatus.APPROVED

    @pytest.mark.asyncio
    async def test_wait_for_approval_timeout(self):
        """Should timeout if approval not received."""
        manager = DiffApprovalManager()

        approval = await manager.create_write_approval(
            session_id="test-session",
            agent_id="coder",
            task_id="task-1",
            file_path="test.py",
            original_content="",
            new_content="new content",
            timeout_seconds=0.1,  # Very short timeout
        )

        # Wait should timeout
        with pytest.raises(asyncio.TimeoutError):
            await manager.wait_for_approval(approval.id, timeout=0.1)

    def test_get_pending_approvals(self):
        """Should list pending approvals."""
        manager = DiffApprovalManager()

        # Create some approvals synchronously (using internal method)
        import uuid
        approval1 = PendingApproval(
            id=str(uuid.uuid4()),
            action_type="write",
            session_id="session-1",
            agent_id="coder",
            task_id="task-1",
        )
        approval2 = PendingApproval(
            id=str(uuid.uuid4()),
            action_type="write",
            session_id="session-1",
            agent_id="coder",
            task_id="task-2",
        )
        approval3 = PendingApproval(
            id=str(uuid.uuid4()),
            action_type="write",
            session_id="session-2",
            agent_id="coder",
            task_id="task-3",
        )

        manager._pending[approval1.id] = approval1
        manager._pending[approval2.id] = approval2
        manager._pending[approval3.id] = approval3

        # Get all pending
        all_pending = manager.get_pending()
        assert len(all_pending) == 3

        # Get pending for session-1
        session1_pending = manager.get_pending(session_id="session-1")
        assert len(session1_pending) == 2

    def test_diff_approval_policy_protected_paths(self):
        """Should identify protected paths correctly."""
        policy = DiffApprovalPolicy(
            enabled=True,
            protected_paths=["*.py", "*.yaml", "*.yml", "Dockerfile*"],
        )

        # Python files are protected
        assert policy.requires_approval("write", "test.py")
        assert policy.requires_approval("write", "/path/to/module.py")

        # YAML files are protected
        assert policy.requires_approval("write", "config.yaml")
        assert policy.requires_approval("write", "docker-compose.yml")

        # Dockerfiles are protected
        assert policy.requires_approval("write", "Dockerfile")
        assert policy.requires_approval("write", "Dockerfile.dev")

        # Other files are not
        assert not policy.requires_approval("write", "readme.md")
        assert not policy.requires_approval("write", "data.csv")


# =============================================================================
# Test: Agent Policies Configuration
# =============================================================================

class TestAgentPolicies:
    """Test agent policy configurations."""

    def test_all_agents_have_policies(self):
        """All expected agents should have policies defined."""
        expected_agents = ["mo", "architect", "coder", "reviewer", "tester", "docs", "devops"]

        for agent_id in expected_agents:
            policy = get_agent_policy(agent_id)
            assert policy is not None
            assert policy.agent_id == agent_id

    def test_unknown_agent_gets_default(self):
        """Unknown agent should get coder policy as default."""
        policy = get_agent_policy("unknown-agent")

        # Should fall back to coder
        assert policy.agent_id == "coder"

    def test_devops_requires_approval(self):
        """DevOps agent should have diff approval enabled."""
        devops = get_agent_policy("devops")

        assert devops.diff_approval.enabled is True
        assert devops.diff_approval.require_approval_for_writes is True
        assert devops.diff_approval.require_approval_for_shell is True

    def test_policy_prompt_generation(self):
        """Should generate policy section for system prompt."""
        coder = get_agent_policy("coder")
        prompt_section = coder.to_prompt_section()

        assert "## TOOL POLICY" in prompt_section
        assert "Allowed Tools" in prompt_section
        assert "## BUDGET LIMITS" in prompt_section

    def test_mo_can_spawn_subagents(self):
        """MO should be able to spawn subagents."""
        mo = get_agent_policy("mo")

        assert mo.budget.max_spawned_tasks_per_run > 0
        assert mo.budget.max_nested_spawn_depth > 0


# =============================================================================
# Test: Interpreter Context with Enterprise Guardrails
# =============================================================================

class TestInterpreterContext:
    """Test InterpreterContext with guardrails integration."""

    def test_context_from_agent_id(self):
        """Should create context with correct agent policy."""
        context = InterpreterContext.from_agent_id(
            agent_id="coder",
            session_id="test-session",
            task_id="test-task",
        )

        assert context.agent_id == "coder"
        assert context.session_id == "test-session"
        assert context.agent_policy is not None
        assert context.budget_tracker is not None
        assert context.agent_policy.agent_id == "coder"

    def test_context_syncs_policy(self):
        """Context should sync basic policy from agent policy."""
        context = InterpreterContext.from_agent_id(agent_id="reviewer")

        # Should sync allowed tools
        assert context.policy.allowed_tools == context.agent_policy.allowed_tools

    def test_context_budget_tracker_initialized(self):
        """Budget tracker should be initialized from agent policy."""
        context = InterpreterContext.from_agent_id(agent_id="coder")

        # Budget tracker should match agent policy limits
        remaining = context.budget_tracker.get_remaining()
        assert remaining["tool_loops"] == context.agent_policy.budget.max_tool_loops_per_message


# =============================================================================
# Test: Tool Interpreter Integration
# =============================================================================

class TestToolInterpreterIntegration:
    """Test ToolInterpreter with guardrails integration."""

    def test_interpreter_for_agent(self):
        """Should create interpreter with agent policy."""
        interpreter = ToolInterpreter.for_agent(
            agent_id="coder",
            session_id="test-session",
        )

        assert interpreter.context.agent_id == "coder"
        assert interpreter.context.budget_tracker is not None

    def test_interpreter_budget_check(self):
        """Should check budget limits on iteration."""
        interpreter = ToolInterpreter.for_agent(
            agent_id="coder",
            session_id="test-session",
        )

        # Initially should be able to continue
        can_continue, error = interpreter.check_iteration_limit()
        assert can_continue is True
        assert error is None

        # Exhaust the budget
        max_loops = interpreter.context.agent_policy.budget.max_tool_loops_per_message
        for _ in range(max_loops):
            interpreter.increment_iteration()

        # Should fail now
        can_continue, error = interpreter.check_iteration_limit()
        assert can_continue is False
        assert error is not None

    def test_interpreter_reset_counters(self):
        """Should reset message counters."""
        interpreter = ToolInterpreter.for_agent(
            agent_id="coder",
            session_id="test-session",
        )

        # Use some budget
        interpreter.increment_iteration()
        interpreter.increment_iteration()

        # Reset
        interpreter.reset_message_counters()

        # Should be fresh again
        assert interpreter.context.iteration == 0
        remaining = interpreter.context.budget_tracker.get_remaining()
        max_loops = interpreter.context.agent_policy.budget.max_tool_loops_per_message
        assert remaining["tool_loops"] == max_loops

    def test_interpreter_summary_includes_budget(self):
        """Summary should include budget usage."""
        interpreter = ToolInterpreter.for_agent(
            agent_id="coder",
            session_id="test-session",
        )

        interpreter.increment_iteration()

        summary = interpreter.get_summary()

        assert "budget_usage" in summary
        assert summary["budget_usage"]["usage"]["tool_loops"] == 1
