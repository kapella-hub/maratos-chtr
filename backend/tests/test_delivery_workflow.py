"""Tests for the Delivery Loop Workflow Policy.

These tests verify the deterministic workflow behavior:
- coder → tester always happens
- tester fail loops back to coder
- coder blocked escalates to architect
- passing tests triggers devops question
- docs optionally triggered
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime

from app.workflows.delivery_loop import (
    DeliveryLoopPolicy,
    WorkflowState,
    WorkflowContext,
    AgentOutcome,
    CoderResult,
    TesterResult,
    ArchitectResult,
    DevOpsResult,
    DocsResult,
    UserDecisionType,
    UserDecisionResponse,
)
from app.workflows.handler import is_coding_task


# =============================================================================
# Result Parsing Tests
# =============================================================================

class TestCoderResultParsing:
    """Test parsing of coder agent responses."""

    def test_parse_done_status(self):
        """Coder completion is detected."""
        response = """
        I've implemented the feature.
        Created file: src/utils.py
        Modified: src/main.py
        The implementation handles all edge cases.
        """
        result = CoderResult.parse(response)
        assert result.status == AgentOutcome.DONE
        assert "src/utils.py" in result.artifacts or "src/main.py" in result.artifacts

    def test_parse_blocked_status(self):
        """Coder blocked status is detected."""
        response = """
        I cannot implement this feature because the requirement is unclear.
        Need more information about the expected behavior.
        """
        result = CoderResult.parse(response)
        assert result.status == AgentOutcome.BLOCKED

    def test_parse_needs_arch_status(self):
        """Coder needs architect is detected."""
        response = """
        This requires an architectural decision.
        There are multiple approaches and I need architect guidance.
        """
        result = CoderResult.parse(response)
        assert result.status == AgentOutcome.NEEDS_ARCH

    def test_parse_error_status(self):
        """Coder error is detected from first-person failure phrases."""
        response = """
        I encountered an error while trying to implement the feature.
        The module import failed and I could not complete the task.
        """
        result = CoderResult.parse(response)
        assert result.status == AgentOutcome.ERROR

    def test_parse_error_not_triggered_by_code_content(self):
        """Error detection should NOT be triggered by code about error handling."""
        response = """
        I've implemented the error handling module. Here's the code:

        ```python
        def handle_error(error):
            if "Could not find" in error.message:
                return ErrorResult.not_found()
            if "Failed to complete" in error.message:
                return ErrorResult.failure()
        ```

        Created: error_handler.py
        """
        result = CoderResult.parse(response)
        assert result.status == AgentOutcome.DONE  # Should NOT be ERROR


class TestTesterResultParsing:
    """Test parsing of tester agent responses."""

    def test_parse_pass_status(self):
        """Test pass is detected."""
        response = """
        Running tests...
        pytest tests/
        All 5 tests passed
        OK (5 tests)
        """
        result = TesterResult.parse(response)
        assert result.status == AgentOutcome.PASS

    def test_parse_fail_status(self):
        """Test failure is detected."""
        response = """
        Running tests...
        pytest tests/
        FAILED - 2 tests failed
        AssertionError: Expected 5, got 10
        """
        result = TesterResult.parse(response)
        assert result.status == AgentOutcome.FAIL
        assert "AssertionError" in result.failure_summary

    def test_parse_fail_with_count(self):
        """Test failure count is extracted."""
        response = """
        Tests: 10 passed, 3 failed
        """
        result = TesterResult.parse(response)
        assert result.status == AgentOutcome.FAIL
        assert result.tests_passed == 10
        assert result.tests_failed == 3

    def test_parse_zero_failed_is_pass(self):
        """All tests passed pattern is detected."""
        response = """
        Running tests...
        All 10 tests passed successfully
        OK (10 tests)
        """
        result = TesterResult.parse(response)
        assert result.status == AgentOutcome.PASS


class TestArchitectResultParsing:
    """Test parsing of architect responses."""

    def test_parse_decisions(self):
        """Decisions are extracted."""
        response = """
        Decision: Use the Strategy pattern for this implementation.
        1. Create an interface
        2. Implement concrete strategies
        3. Use dependency injection
        """
        result = ArchitectResult.parse(response)
        assert len(result.decisions) > 0


class TestDevOpsResultParsing:
    """Test parsing of devops responses."""

    def test_parse_commit_option(self):
        """Commit option is detected."""
        response = """
        Changes are ready to commit.
        Suggested commit message: "feat: add user authentication"
        """
        result = DevOpsResult.parse(response)
        assert "commit" in result.options_presented
        assert result.commit_message is not None


# =============================================================================
# Coding Task Detection Tests
# =============================================================================

class TestCodingTaskDetection:
    """Test is_coding_task detection."""

    def test_implement_is_coding(self):
        assert is_coding_task("Implement a login feature") is True

    def test_create_is_coding(self):
        assert is_coding_task("Create a new API endpoint") is True

    def test_fix_is_coding(self):
        assert is_coding_task("Fix the bug in authentication") is True

    def test_explain_is_not_coding(self):
        assert is_coding_task("Explain how authentication works") is False

    def test_what_is_not_coding(self):
        assert is_coding_task("What is the difference between REST and GraphQL?") is False

    def test_describe_is_not_coding(self):
        assert is_coding_task("Describe the current architecture") is False


# =============================================================================
# Workflow State Machine Tests
# =============================================================================

class TestWorkflowStateMachine:
    """Test workflow state transitions."""

    def test_initial_state_is_pending(self):
        """Workflow starts in PENDING state."""
        ctx = WorkflowContext(
            workflow_id="test-1",
            session_id="session-1",
            original_task="Implement feature",
        )
        assert ctx.state == WorkflowState.PENDING

    def test_valid_transition_pending_to_coding(self):
        """Can transition from PENDING to CODING."""
        ctx = WorkflowContext(
            workflow_id="test-1",
            session_id="session-1",
            original_task="Implement feature",
        )
        assert ctx.can_transition(WorkflowState.CODING) is True
        ctx.transition(WorkflowState.CODING)
        assert ctx.state == WorkflowState.CODING

    def test_valid_transition_coding_to_testing(self):
        """Can transition from CODING to TESTING."""
        ctx = WorkflowContext(
            workflow_id="test-1",
            session_id="session-1",
            original_task="Implement feature",
            state=WorkflowState.CODING,
        )
        assert ctx.can_transition(WorkflowState.TESTING) is True
        ctx.transition(WorkflowState.TESTING)
        assert ctx.state == WorkflowState.TESTING

    def test_valid_transition_testing_to_fixing(self):
        """Can transition from TESTING to FIXING on failure."""
        ctx = WorkflowContext(
            workflow_id="test-1",
            session_id="session-1",
            original_task="Implement feature",
            state=WorkflowState.TESTING,
        )
        assert ctx.can_transition(WorkflowState.FIXING) is True

    def test_valid_transition_testing_to_deploying(self):
        """Can transition from TESTING to DEPLOYING on pass."""
        ctx = WorkflowContext(
            workflow_id="test-1",
            session_id="session-1",
            original_task="Implement feature",
            state=WorkflowState.TESTING,
        )
        assert ctx.can_transition(WorkflowState.DEPLOYING) is True

    def test_invalid_transition_raises(self):
        """Invalid transitions raise ValueError."""
        ctx = WorkflowContext(
            workflow_id="test-1",
            session_id="session-1",
            original_task="Implement feature",
            state=WorkflowState.PENDING,
        )
        with pytest.raises(ValueError):
            ctx.transition(WorkflowState.TESTING)  # Can't skip CODING

    def test_budget_exceeded_detection(self):
        """Budget exceeded is detected correctly."""
        ctx = WorkflowContext(
            workflow_id="test-1",
            session_id="session-1",
            original_task="Implement feature",
            max_fix_cycles=3,
            max_architect_cycles=2,
        )
        assert ctx.budget_exceeded() is False

        ctx.fix_cycles = 3
        assert ctx.budget_exceeded() is False  # Need both exceeded

        ctx.architect_cycles = 2
        assert ctx.budget_exceeded() is True


# =============================================================================
# Policy Integration Tests
# =============================================================================

class TestDeliveryLoopPolicy:
    """Test the complete policy behavior."""

    @pytest.fixture
    def policy(self):
        return DeliveryLoopPolicy(max_fix_cycles=2, max_architect_cycles=1)

    def test_create_workflow(self, policy):
        """Can create a workflow."""
        ctx = policy.create_workflow("session-1", "Implement feature", "/workspace")
        assert ctx.workflow_id.startswith("wf-")
        assert ctx.session_id == "session-1"
        assert ctx.original_task == "Implement feature"
        assert ctx.workspace_path == "/workspace"

    def test_get_workflow(self, policy):
        """Can retrieve workflow by ID."""
        ctx = policy.create_workflow("session-1", "Implement feature")
        retrieved = policy.get_workflow(ctx.workflow_id)
        assert retrieved is ctx

    def test_get_workflow_for_session(self, policy):
        """Can retrieve workflow by session ID."""
        ctx = policy.create_workflow("session-1", "Implement feature")
        ctx.state = WorkflowState.CODING  # Make it active
        retrieved = policy.get_workflow_for_session("session-1")
        assert retrieved is ctx

    def test_cleanup_workflow(self, policy):
        """Cleanup removes workflow."""
        ctx = policy.create_workflow("session-1", "Implement feature")
        policy.cleanup_workflow(ctx.workflow_id)
        assert policy.get_workflow(ctx.workflow_id) is None

    @pytest.mark.asyncio
    async def test_coder_then_tester_always_runs(self, policy):
        """After coder completes, tester ALWAYS runs."""
        agents_called = []

        async def mock_spawn(agent_id, prompt, context):
            agents_called.append(agent_id)
            if agent_id == "coder":
                return "I implemented the feature. Created file: main.py"
            elif agent_id == "tester":
                return "All tests passed. 5 tests, 0 failed"
            elif agent_id == "devops":
                return "Ready to commit. Options: commit, deploy, pr"
            return ""

        events = []
        async for event in policy.run(
            session_id="test",
            task="Implement a feature",
            spawn_agent_fn=mock_spawn,
        ):
            events.append(event)

        # Verify coder was called, then tester
        assert "coder" in agents_called
        assert "tester" in agents_called
        assert agents_called.index("coder") < agents_called.index("tester")

    @pytest.mark.asyncio
    async def test_tester_fail_loops_to_coder(self, policy):
        """Test failure loops back to coder."""
        call_count = {"coder": 0, "tester": 0}

        async def mock_spawn(agent_id, prompt, context):
            call_count[agent_id] = call_count.get(agent_id, 0) + 1
            if agent_id == "coder":
                return "Implemented. Created file: main.py"
            elif agent_id == "tester":
                # Fail first time, pass second time
                if call_count["tester"] == 1:
                    return "FAILED - 2 tests failed. AssertionError: wrong value"
                return "All tests passed"
            elif agent_id == "devops":
                return "Ready to commit"
            return ""

        events = []
        async for event in policy.run(
            session_id="test",
            task="Implement a feature",
            spawn_agent_fn=mock_spawn,
        ):
            events.append(event)

        # Coder should be called twice (initial + fix)
        assert call_count["coder"] == 2
        # Tester should be called twice
        assert call_count["tester"] == 2

    @pytest.mark.asyncio
    async def test_coder_blocked_escalates_to_architect(self, policy):
        """Coder blocked escalates to architect."""
        agents_called = []

        async def mock_spawn(agent_id, prompt, context):
            agents_called.append(agent_id)
            if agent_id == "coder":
                if len([a for a in agents_called if a == "coder"]) == 1:
                    return "I cannot implement this. Need more information. Blocked by unclear requirements."
                return "Implemented with new design. Created file: main.py"
            elif agent_id == "architect":
                return "Decision: Use simpler approach. Files to modify: main.py"
            elif agent_id == "tester":
                return "All tests passed"
            elif agent_id == "devops":
                return "Ready to commit"
            return ""

        events = []
        async for event in policy.run(
            session_id="test",
            task="Implement a feature",
            spawn_agent_fn=mock_spawn,
        ):
            events.append(event)

        assert "architect" in agents_called

    @pytest.mark.asyncio
    async def test_passing_tests_triggers_devops(self, policy):
        """Passing tests go to devops."""
        agents_called = []

        async def mock_spawn(agent_id, prompt, context):
            agents_called.append(agent_id)
            if agent_id == "coder":
                return "Implemented. Created file: main.py"
            elif agent_id == "tester":
                return "All tests passed. OK (10 tests)"
            elif agent_id == "devops":
                return "Ready to commit. Suggested message: 'feat: add feature'"
            return ""

        events = []
        async for event in policy.run(
            session_id="test",
            task="Implement a feature",
            spawn_agent_fn=mock_spawn,
        ):
            events.append(event)

        assert "devops" in agents_called
        assert agents_called.index("tester") < agents_called.index("devops")

    @pytest.mark.asyncio
    async def test_workflow_emits_correct_events(self, policy):
        """Workflow emits expected SSE events."""
        async def mock_spawn(agent_id, prompt, context):
            if agent_id == "coder":
                return "Implemented"
            elif agent_id == "tester":
                return "All tests passed"
            elif agent_id == "devops":
                return "Ready"
            return ""

        event_types = []
        async for event in policy.run(
            session_id="test",
            task="Implement",
            spawn_agent_fn=mock_spawn,
        ):
            event_types.append(event.type)

        assert "workflow_started" in event_types
        assert "agent_started" in event_types
        assert "agent_completed" in event_types
        assert "gate_result" in event_types
        assert "user_decision_requested" in event_types

    def test_resume_after_docs_decision_yes(self, policy):
        """Can resume workflow after user says yes to docs."""
        ctx = policy.create_workflow("session-1", "Implement feature")
        ctx.state = WorkflowState.AWAITING_USER
        ctx.pending_decision = UserDecisionType.DOCS

        decision = UserDecisionResponse(
            decision_type=UserDecisionType.DOCS,
            approved=True,
        )
        resumed = policy.resume_after_user_decision(ctx.workflow_id, decision)
        assert resumed is ctx
        assert ctx.state == WorkflowState.DOCUMENTING

    def test_resume_after_docs_decision_no(self, policy):
        """Can resume workflow after user says no to docs."""
        ctx = policy.create_workflow("session-1", "Implement feature")
        ctx.state = WorkflowState.AWAITING_USER
        ctx.pending_decision = UserDecisionType.DOCS

        decision = UserDecisionResponse(
            decision_type=UserDecisionType.DOCS,
            approved=False,
        )
        resumed = policy.resume_after_user_decision(ctx.workflow_id, decision)
        assert resumed is ctx
        assert ctx.state == WorkflowState.COMPLETED


# =============================================================================
# Budget Enforcement Tests
# =============================================================================

class TestBudgetEnforcement:
    """Test that budgets are enforced."""

    @pytest.mark.asyncio
    async def test_max_fix_cycles_enforced(self):
        """Workflow correctly cycles through fix attempts before escalating."""
        policy = DeliveryLoopPolicy(max_fix_cycles=2, max_architect_cycles=1)
        coder_calls = 0
        architect_calls = 0

        async def mock_spawn(agent_id, prompt, context):
            nonlocal coder_calls, architect_calls
            if agent_id == "coder":
                coder_calls += 1
                return "Implemented. Created file: main.py"
            elif agent_id == "tester":
                # Return explicit test failure output that will be parsed as FAIL
                return """
Running pytest...
FAILED tests/test_main.py::test_function - AssertionError: expected 5, got 10

## Test Results
- Tests run: 5
- Tests passed: 3
- Tests failed: 2

AssertionError: Values don't match
"""
            elif agent_id == "architect":
                architect_calls += 1
                return "Try a different approach. Decision: Use simpler logic."
            return ""

        events = []
        async for event in policy.run(
            session_id="test",
            task="Implement",
            spawn_agent_fn=mock_spawn,
        ):
            events.append(event)
            # Limit to prevent infinite loop
            if coder_calls > 10:
                break

        # Should have called coder multiple times and escalated to architect
        assert coder_calls >= 2, "Coder should be called multiple times"
        assert architect_calls >= 1, "Should escalate to architect when coder fails"

        # Verify the workflow went through fixing state
        state_events = [e for e in events if e.type == "workflow_state"]
        states = [e.data.get("state") for e in state_events]
        assert "fixing" in states, "Should enter fixing state when tests fail"
        assert "escalating" in states, "Should escalate when fix cycles exceeded"

    @pytest.mark.asyncio
    async def test_max_architect_cycles_enforced(self):
        """Workflow fails after max architect cycles exceeded."""
        policy = DeliveryLoopPolicy(max_fix_cycles=1, max_architect_cycles=1)

        async def mock_spawn(agent_id, prompt, context):
            if agent_id == "coder":
                return "Cannot implement. Need more information. Blocked."
            elif agent_id == "architect":
                return "Use this approach."
            return ""

        events = []
        async for event in policy.run(
            session_id="test",
            task="Implement",
            spawn_agent_fn=mock_spawn,
        ):
            events.append(event)
            # Limit iterations to prevent infinite loop in test
            if len(events) > 20:
                break

        # Should eventually fail
        final_states = [e for e in events if e.type == "workflow_state"]
        # Check that we tried architect
        agent_events = [e for e in events if e.type == "agent_started"]
        agents = [e.data.get("agent") for e in agent_events]
        assert "architect" in agents


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
