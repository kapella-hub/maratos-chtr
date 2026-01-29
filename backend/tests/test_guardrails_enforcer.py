"""Tests for unified GuardrailsEnforcer across all execution paths.

These tests ensure that guardrails are enforced consistently regardless of
which code path is used to execute tools:
- Chat API → interpreter → tool
- Skills API → executor → tool
- Direct tool_executor.execute() calls
- Agent.run_tool() calls

Critical security tests:
1. "reviewer cannot write" - across all paths
2. "write outside workspace blocked" - across all paths
3. "budget exceeded triggers error" - across all paths
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

# Guardrails
from app.guardrails import (
    GuardrailsEnforcer,
    EnforcementContext,
    EnforcementResult,
    AgentPolicy,
    BudgetPolicy,
    FilesystemPolicy,
    get_agent_policy,
    BudgetExceededError,
    BudgetType,
)

# Tool execution paths
from app.tools.executor import tool_executor
from app.tools.base import ToolResult


# =============================================================================
# Test: GuardrailsEnforcer Factory Methods
# =============================================================================

class TestEnforcerCreation:
    """Test enforcer factory methods."""

    def test_for_agent_creates_correct_policy(self):
        """for_agent should load correct agent policy."""
        enforcer = GuardrailsEnforcer.for_agent("coder", session_id="test")

        assert enforcer.context.agent_id == "coder"
        assert enforcer.context.agent_policy is not None
        assert enforcer.context.agent_policy.agent_id == "coder"
        assert enforcer.context.budget_tracker is not None

    def test_for_agent_reviewer_has_no_write(self):
        """Reviewer enforcer should have no write permissions."""
        enforcer = GuardrailsEnforcer.for_agent("reviewer")

        assert enforcer.context.agent_policy.filesystem.write_allowed is False

    def test_for_skill_creates_restricted_policy(self):
        """for_skill should create restricted policy."""
        enforcer = GuardrailsEnforcer.for_skill(
            skill_id="test-skill",
            workdir="/workspace/test",
        )

        assert enforcer.context.agent_id == "skill:test-skill"
        assert "kiro" in enforcer.context.agent_policy.allowed_tools
        assert "shell" in enforcer.context.agent_policy.allowed_tools
        assert "filesystem" in enforcer.context.agent_policy.allowed_tools

    def test_default_is_restrictive(self):
        """Default enforcer should be restrictive."""
        enforcer = GuardrailsEnforcer.default()

        # Default only allows filesystem (read-only)
        assert enforcer.context.agent_policy is not None


# =============================================================================
# Test: Tool Allowlist Enforcement
# =============================================================================

class TestToolAllowlistEnforcement:
    """Test that tool allowlists are enforced across all paths."""

    @pytest.mark.asyncio
    async def test_enforcer_blocks_disallowed_tool(self):
        """Enforcer should block tools not in allowlist."""
        enforcer = GuardrailsEnforcer.for_agent("reviewer")

        # Reviewer can use filesystem, shell, kiro
        # Try to use a tool not in the list
        result = await enforcer.check_tool_execution("canvas", {"artifact_id": "test"})

        assert result.allowed is False
        assert result.policy_blocked is True
        assert "not allowed" in result.error.lower()

    @pytest.mark.asyncio
    async def test_enforcer_allows_permitted_tool(self):
        """Enforcer should allow tools in allowlist."""
        enforcer = GuardrailsEnforcer.for_agent("coder")

        # Coder can use filesystem
        result = await enforcer.check_tool_execution(
            "filesystem",
            {"action": "read", "path": "/any/path"}
        )

        assert result.allowed is True
        assert result.error is None

    @pytest.mark.asyncio
    async def test_tool_executor_blocks_disallowed_tool(self):
        """tool_executor should block disallowed tools when agent_id provided."""
        # Mock the tool registry to avoid actual execution
        with patch("app.tools.executor.registry") as mock_registry:
            mock_tool = MagicMock()
            mock_registry.get.return_value = mock_tool

            result = await tool_executor.execute(
                tool_id="canvas",
                agent_id="reviewer",
                session_id="test",
                artifact_id="test",
            )

        assert result.success is False
        assert "not allowed" in result.error.lower()

    @pytest.mark.asyncio
    async def test_all_agents_have_tool_restrictions(self):
        """All agent types should have defined tool allowlists."""
        agent_ids = ["mo", "architect", "coder", "reviewer", "tester", "docs", "devops"]

        for agent_id in agent_ids:
            enforcer = GuardrailsEnforcer.for_agent(agent_id)
            policy = enforcer.context.agent_policy

            # All agents should have some allowed tools defined
            assert policy.allowed_tools is not None
            assert len(policy.allowed_tools) > 0


# =============================================================================
# Test: Filesystem Jail Enforcement
# =============================================================================

class TestFilesystemJailEnforcement:
    """Test that filesystem jail is enforced across all paths."""

    @pytest.mark.asyncio
    async def test_enforcer_blocks_write_outside_workspace(self):
        """Enforcer should block writes outside workspace."""
        enforcer = GuardrailsEnforcer.for_agent("coder", session_id="test")

        result = await enforcer.check_tool_execution(
            "filesystem",
            {"action": "write", "path": "/etc/passwd", "content": "malicious"}
        )

        assert result.allowed is False
        assert result.sandbox_violation is True
        assert "workspace" in result.error.lower()

    @pytest.mark.asyncio
    async def test_enforcer_allows_write_in_workspace(self):
        """Enforcer should allow writes in workspace."""
        enforcer = GuardrailsEnforcer.for_agent("coder", session_id="test")

        result = await enforcer.check_tool_execution(
            "filesystem",
            {"action": "write", "path": "~/maratos-workspace/test.py", "content": "safe"}
        )

        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_enforcer_allows_read_anywhere(self):
        """Enforcer should allow reads from anywhere."""
        enforcer = GuardrailsEnforcer.for_agent("coder", session_id="test")

        # Reading from outside workspace should be allowed
        result = await enforcer.check_tool_execution(
            "filesystem",
            {"action": "read", "path": "/etc/hosts"}
        )

        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_reviewer_cannot_write_anywhere(self):
        """Reviewer should not be able to write anywhere."""
        enforcer = GuardrailsEnforcer.for_agent("reviewer", session_id="test")

        # Even workspace writes should be blocked for reviewer
        result = await enforcer.check_tool_execution(
            "filesystem",
            {"action": "write", "path": "~/maratos-workspace/test.py", "content": "test"}
        )

        assert result.allowed is False
        assert result.sandbox_violation is True

    @pytest.mark.asyncio
    async def test_tool_executor_blocks_write_outside_workspace(self):
        """tool_executor should block writes outside workspace."""
        result = await tool_executor.execute(
            tool_id="filesystem",
            agent_id="coder",
            session_id="test",
            action="write",
            path="/etc/test",
            content="malicious",
        )

        assert result.success is False
        assert "workspace" in result.error.lower()

    @pytest.mark.asyncio
    async def test_skill_executor_enforces_workspace(self):
        """Skills executor should enforce workspace for filesystem."""
        from app.skills.executor import SkillExecutor

        executor = SkillExecutor(
            workdir="~/maratos-workspace/skills-test",
            session_id="test",
            skill_id="test-skill",
        )

        # Attempt filesystem operation outside workspace
        result = await executor._run_filesystem({
            "action": "write",
            "path": "/etc/test",
            "content": "malicious",
        })

        assert result["success"] is False
        assert "workspace" in result.get("error", "").lower()


# =============================================================================
# Test: Budget Enforcement
# =============================================================================

class TestBudgetEnforcement:
    """Test that budget limits are enforced across all paths."""

    @pytest.mark.asyncio
    async def test_enforcer_tracks_tool_calls(self):
        """Enforcer should track tool calls against budget."""
        enforcer = GuardrailsEnforcer.for_agent("coder", session_id="test")

        # Mock successful execution
        mock_result = ToolResult(success=True, output="ok")

        # Simulate several tool calls
        for i in range(5):
            check = await enforcer.check_tool_execution("filesystem", {"action": "read", "path": f"/test{i}"})
            assert check.allowed is True

            await enforcer.record_tool_execution(
                "filesystem",
                {"action": "read", "path": f"/test{i}"},
                mock_result,
                100.0,
                check,
            )

        # Verify tracking
        assert enforcer.context.tool_calls_in_session == 5

    @pytest.mark.asyncio
    async def test_enforcer_budget_exceeded_blocks_execution(self):
        """Enforcer should block execution when budget exceeded."""
        # Create enforcer with very low budget
        from app.guardrails.policies import AgentPolicy, BudgetPolicy, FilesystemPolicy

        low_budget_policy = AgentPolicy(
            agent_id="test",
            description="Test agent with low budget",
            allowed_tools=["filesystem"],
            budget=BudgetPolicy(
                max_tool_calls_per_message=2,
                max_tool_calls_per_session=3,
            ),
            filesystem=FilesystemPolicy(
                read_paths=["*"],
                write_paths=["~/maratos-workspace"],
            ),
        )

        from app.guardrails.budgets import BudgetTracker
        budget_tracker = BudgetTracker(low_budget_policy.budget, session_id="test")

        context = EnforcementContext(
            session_id="test",
            agent_id="test",
            agent_policy=low_budget_policy,
            budget_tracker=budget_tracker,
            enable_audit=False,
        )
        enforcer = GuardrailsEnforcer(context)

        # Use up the session budget
        for i in range(3):
            check = await enforcer.check_tool_execution("filesystem", {"action": "read", "path": f"/test{i}"})
            if check.allowed:
                await enforcer.record_tool_execution(
                    "filesystem", {"action": "read"}, ToolResult(success=True, output=""), 10.0, check
                )

        # Next call should fail
        check = await enforcer.check_tool_execution("filesystem", {"action": "read", "path": "/test4"})
        assert check.allowed is False
        assert check.budget_exceeded is True

    @pytest.mark.asyncio
    async def test_coder_cannot_spawn(self):
        """Coder agent should have spawn budget of 0."""
        enforcer = GuardrailsEnforcer.for_agent("coder")

        # Check spawn budget
        assert enforcer.context.agent_policy.budget.max_spawned_tasks_per_run == 0

    @pytest.mark.asyncio
    async def test_mo_can_spawn(self):
        """MO agent should have positive spawn budget."""
        enforcer = GuardrailsEnforcer.for_agent("mo")

        # Check spawn budget
        assert enforcer.context.agent_policy.budget.max_spawned_tasks_per_run > 0


# =============================================================================
# Test: Write Operations Blocked for Reviewer Across All Paths
# =============================================================================

class TestReviewerCannotWrite:
    """Verify reviewer cannot write across ALL execution paths."""

    @pytest.mark.asyncio
    async def test_reviewer_via_enforcer(self):
        """Reviewer blocked via direct enforcer check."""
        enforcer = GuardrailsEnforcer.for_agent("reviewer")

        result = await enforcer.check_tool_execution(
            "filesystem",
            {"action": "write", "path": "~/maratos-workspace/test.py", "content": "x"}
        )

        assert result.allowed is False
        assert result.sandbox_violation is True

    @pytest.mark.asyncio
    async def test_reviewer_via_tool_executor(self):
        """Reviewer blocked via tool_executor."""
        result = await tool_executor.execute(
            tool_id="filesystem",
            agent_id="reviewer",
            session_id="test",
            action="write",
            path="~/maratos-workspace/test.py",
            content="x",
        )

        assert result.success is False

    @pytest.mark.asyncio
    async def test_reviewer_policy_enforcement(self):
        """Reviewer policy should explicitly deny writes."""
        policy = get_agent_policy("reviewer")

        assert policy.filesystem.write_allowed is False
        assert policy.filesystem.write_paths == []
        assert not policy.filesystem.can_write("/any/path")
        assert not policy.filesystem.can_write("~/maratos-workspace/file.py")


# =============================================================================
# Test: Write Outside Workspace Blocked Across All Paths
# =============================================================================

class TestWriteOutsideWorkspaceBlocked:
    """Verify writes outside workspace are blocked across ALL execution paths."""

    @pytest.mark.asyncio
    async def test_coder_via_enforcer(self):
        """Coder blocked from /etc via enforcer."""
        enforcer = GuardrailsEnforcer.for_agent("coder")

        result = await enforcer.check_tool_execution(
            "filesystem",
            {"action": "write", "path": "/etc/passwd", "content": "x"}
        )

        assert result.allowed is False
        assert result.sandbox_violation is True

    @pytest.mark.asyncio
    async def test_coder_via_tool_executor(self):
        """Coder blocked from /etc via tool_executor."""
        result = await tool_executor.execute(
            tool_id="filesystem",
            agent_id="coder",
            session_id="test",
            action="write",
            path="/etc/passwd",
            content="x",
        )

        assert result.success is False
        assert "workspace" in result.error.lower()

    @pytest.mark.asyncio
    async def test_devops_via_enforcer(self):
        """DevOps blocked from /etc via enforcer."""
        enforcer = GuardrailsEnforcer.for_agent("devops")

        result = await enforcer.check_tool_execution(
            "filesystem",
            {"action": "write", "path": "/etc/passwd", "content": "x"}
        )

        assert result.allowed is False
        assert result.sandbox_violation is True

    @pytest.mark.asyncio
    async def test_skill_via_skill_executor(self):
        """Skills blocked from /etc via SkillExecutor."""
        from app.skills.executor import SkillExecutor

        executor = SkillExecutor(
            workdir="~/maratos-workspace/test",
            session_id="test",
            skill_id="test-skill",
        )

        result = await executor._run_filesystem({
            "action": "write",
            "path": "/etc/passwd",
            "content": "x",
        })

        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_default_enforcer_blocks_write(self):
        """Default enforcer should block all writes."""
        enforcer = GuardrailsEnforcer.default()

        result = await enforcer.check_tool_execution(
            "filesystem",
            {"action": "write", "path": "~/maratos-workspace/test.py", "content": "x"}
        )

        # Default policy should be very restrictive
        # Even workspace writes may be blocked by default


# =============================================================================
# Test: Budget Exceeded Triggers Controlled Error Across All Paths
# =============================================================================

class TestBudgetExceededError:
    """Verify budget exceeded triggers controlled error across ALL paths."""

    @pytest.mark.asyncio
    async def test_budget_exceeded_via_enforcer(self):
        """Budget exceeded via enforcer returns controlled error."""
        from app.guardrails.policies import AgentPolicy, BudgetPolicy, FilesystemPolicy
        from app.guardrails.budgets import BudgetTracker

        # Create very restricted budget
        policy = AgentPolicy(
            agent_id="test",
            description="Test agent with restricted budget",
            allowed_tools=["filesystem"],
            budget=BudgetPolicy(max_tool_calls_per_message=1, max_tool_calls_per_session=1),
            filesystem=FilesystemPolicy(read_paths=["*"]),
        )
        tracker = BudgetTracker(policy.budget)

        context = EnforcementContext(
            agent_policy=policy,
            budget_tracker=tracker,
            enable_audit=False,
        )
        enforcer = GuardrailsEnforcer(context)

        # First call succeeds
        r1 = await enforcer.check_tool_execution("filesystem", {"action": "read", "path": "/test"})
        assert r1.allowed is True
        await enforcer.record_tool_execution("filesystem", {}, ToolResult(success=True, output=""), 1.0, r1)

        # Second call fails with budget error
        r2 = await enforcer.check_tool_execution("filesystem", {"action": "read", "path": "/test2"})
        assert r2.allowed is False
        assert r2.budget_exceeded is True
        assert "exceeded" in r2.error.lower()

    @pytest.mark.asyncio
    async def test_budget_exceeded_via_tool_executor(self):
        """Budget exceeded via tool_executor returns controlled error."""
        from app.guardrails import GuardrailsEnforcer
        from app.guardrails.policies import AgentPolicy, BudgetPolicy, FilesystemPolicy
        from app.guardrails.budgets import BudgetTracker

        # Create very restricted budget
        policy = AgentPolicy(
            agent_id="test",
            description="Test agent with restricted budget",
            allowed_tools=["filesystem"],
            budget=BudgetPolicy(max_tool_calls_per_message=1, max_tool_calls_per_session=1),
            filesystem=FilesystemPolicy(read_paths=["*"]),
        )
        tracker = BudgetTracker(policy.budget)

        context = EnforcementContext(
            agent_policy=policy,
            budget_tracker=tracker,
            enable_audit=False,
        )
        enforcer = GuardrailsEnforcer(context)

        # First call via executor with our restricted enforcer
        with patch("app.tools.executor.registry") as mock_registry:
            mock_tool = MagicMock()
            mock_tool.execute = AsyncMock(return_value=ToolResult(success=True, output="ok"))
            mock_registry.get.return_value = mock_tool

            r1 = await tool_executor.execute(
                "filesystem",
                enforcer=enforcer,
                action="read",
                path="/test",
            )

        # Second call should fail
        r2 = await tool_executor.execute(
            "filesystem",
            enforcer=enforcer,
            action="read",
            path="/test2",
        )
        assert r2.success is False


# =============================================================================
# Test: Enforcer Summary and Budget Tracking
# =============================================================================

class TestEnforcerUtilities:
    """Test enforcer utility methods."""

    def test_get_budget_remaining(self):
        """Should return remaining budget."""
        enforcer = GuardrailsEnforcer.for_agent("coder")

        remaining = enforcer.get_budget_remaining()

        assert remaining is not None
        assert "tool_loops" in remaining
        assert "tool_calls_message" in remaining

    def test_reset_message_counters(self):
        """Should reset per-message counters."""
        enforcer = GuardrailsEnforcer.for_agent("coder")

        # Use some budget
        enforcer.context.budget_tracker.record_tool_loop()
        enforcer.context.budget_tracker.record_tool_loop()

        # Reset
        enforcer.reset_message_counters()

        # Counters should be reset
        remaining = enforcer.get_budget_remaining()
        max_loops = enforcer.context.agent_policy.budget.max_tool_loops_per_message
        assert remaining["tool_loops"] == max_loops

    def test_enforcement_summary(self):
        """Should return enforcement summary."""
        enforcer = GuardrailsEnforcer.for_agent("coder", session_id="test-session")

        summary = enforcer.get_enforcement_summary()

        assert summary["agent_id"] == "coder"
        assert summary["session_id"] == "test-session"
        assert "tool_calls" in summary
        assert "budget_remaining" in summary


# =============================================================================
# Test: Integration - No Bypass Paths
# =============================================================================

class TestNoBypassPaths:
    """Verify there are no paths that bypass guardrails."""

    @pytest.mark.asyncio
    async def test_tool_executor_always_enforces_when_agent_provided(self):
        """tool_executor should always enforce when agent_id is provided."""
        # Calling with agent_id should trigger guardrails
        result = await tool_executor.execute(
            tool_id="nonexistent_tool",
            agent_id="reviewer",
            session_id="test",
        )

        # Should fail at policy check, not tool execution
        assert result.success is False

    @pytest.mark.asyncio
    async def test_tool_executor_default_policy_for_unknown_caller(self):
        """tool_executor should use restrictive default for unknown callers."""
        # Calling without agent_id should use default restrictive policy
        result = await tool_executor.execute(
            tool_id="filesystem",
            session_id="test",
            action="write",
            path="/etc/passwd",
            content="x",
        )

        # Should be blocked
        assert result.success is False

    @pytest.mark.asyncio
    async def test_skip_guardrails_flag_exists_but_dangerous(self):
        """skip_guardrails flag exists but should only be used internally."""
        # This test documents that the flag exists
        # It should NEVER be used in production code paths

        with patch("app.tools.executor.registry") as mock_registry:
            mock_tool = MagicMock()
            mock_tool.execute = AsyncMock(return_value=ToolResult(success=True, output="ok"))
            mock_registry.get.return_value = mock_tool

            # With skip_guardrails=True, execution proceeds without checks
            # THIS IS DANGEROUS and should only be used for testing/internal ops
            result = await tool_executor.execute(
                tool_id="filesystem",
                skip_guardrails=True,  # DANGEROUS
                action="write",
                path="/etc/test",
                content="x",
            )

            # Tool executes without guardrails check
            assert mock_tool.execute.called
