"""Tests for the Workflow Decision Gates.

These tests verify the end-of-loop gate behavior:
- DevOps asks user about commit, PR, deploy
- User decisions are captured correctly
- Artifact report is generated
- Docs agent is triggered optionally
- Declining still produces final report
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime

from app.workflows.delivery_loop import (
    DeliveryLoopPolicy,
    WorkflowState,
    WorkflowContext,
    AgentOutcome,
    DevOpsResult,
    DocsResult,
    UserDecision,
    UserDecisionType,
    UserDecisionResponse,
    ArtifactReport,
    WorkflowEvent,
)
from app.workflows.handler import (
    parse_user_decision_from_message,
)


# =============================================================================
# DevOpsResult Parsing Tests
# =============================================================================

class TestDevOpsResultParsing:
    """Test parsing of devops agent responses."""

    def test_parse_commit_option(self):
        """Commit option is detected."""
        response = """
        Changes are ready to commit.
        Suggested commit message: "feat: add user authentication"
        """
        result = DevOpsResult.parse(response)
        assert "commit" in result.options_presented
        assert result.commit_message == "feat: add user authentication"

    def test_parse_pr_option(self):
        """PR option is detected."""
        response = """
        You can create a pull request for review.
        Branch: feature/auth
        """
        result = DevOpsResult.parse(response)
        assert "pr" in result.options_presented
        assert result.branch_name == "feature/auth"

    def test_parse_deploy_option(self):
        """Deploy option is detected."""
        response = """
        Deploy is available.
        Environments: staging, production
        """
        result = DevOpsResult.parse(response)
        assert "deploy" in result.options_presented
        assert result.deploy_available is True
        assert "staging" in result.deploy_environments

    def test_parse_files_changed(self):
        """Files changed are extracted."""
        response = """
        ## Files Changed
        - modified: src/auth.py
        - changed: src/user.py
        - created: src/utils.py
        """
        result = DevOpsResult.parse(response)
        assert "src/auth.py" in result.files_changed
        assert "src/user.py" in result.files_changed

    def test_parse_diff_summary(self):
        """Diff summary is extracted."""
        response = """
        ## Git Diff
        ```diff
        + def new_function():
        +     return True
        - def old_function():
        -     pass
        ```
        """
        result = DevOpsResult.parse(response)
        assert "new_function" in result.diff_summary

    def test_parse_conventional_commit_message(self):
        """Conventional commit message is extracted."""
        response = """
        Suggested message: "fix: resolve authentication bug"
        """
        result = DevOpsResult.parse(response)
        assert result.commit_message == "fix: resolve authentication bug"


# =============================================================================
# User Decision Parsing Tests
# =============================================================================

class TestUserDecisionParsing:
    """Test parsing user responses into structured decisions."""

    def test_parse_yes_response(self):
        """Affirmative responses are detected."""
        for response in ["yes", "y", "yeah", "sure", "ok", "okay", "go"]:
            decision = parse_user_decision_from_message(response, UserDecisionType.COMMIT)
            assert decision.approved is True, f"'{response}' should be approved"

    def test_parse_no_response(self):
        """Negative responses are detected."""
        for response in ["no", "n", "nope", "skip", "cancel", "don't"]:
            decision = parse_user_decision_from_message(response, UserDecisionType.COMMIT)
            assert decision.approved is False, f"'{response}' should not be approved"

    def test_parse_commit_with_custom_message(self):
        """Custom commit message in response is captured."""
        decision = parse_user_decision_from_message(
            "yes, commit with message: feat: add login feature",
            UserDecisionType.COMMIT
        )
        assert decision.approved is True

    def test_parse_branch_name(self):
        """Branch name in response is captured."""
        decision = parse_user_decision_from_message(
            "yes, branch: feature/my-branch",
            UserDecisionType.COMMIT
        )
        assert decision.approved is True
        assert decision.metadata.get("branch_name") == "feature/my-branch"

    def test_parse_deploy_environment(self):
        """Deploy environment in response is captured."""
        decision = parse_user_decision_from_message(
            "yes, deploy to staging",
            UserDecisionType.DEPLOY
        )
        assert decision.approved is True
        assert decision.value == "staging"

    def test_parse_docs_decision(self):
        """Docs decision parsing."""
        decision = parse_user_decision_from_message("yes, document it", UserDecisionType.DOCS)
        assert decision.approved is True

        decision = parse_user_decision_from_message("skip docs", UserDecisionType.DOCS)
        assert decision.approved is False


# =============================================================================
# Artifact Report Tests
# =============================================================================

class TestArtifactReport:
    """Test artifact report generation."""

    def test_report_to_dict(self):
        """Report can be converted to dict."""
        report = ArtifactReport(
            workflow_id="wf-123",
            task="Implement login",
            status="completed",
            files_created=["src/auth.py"],
            files_modified=["src/main.py"],
            tests_run=5,
            tests_passed=5,
            summary="Implementation complete",
        )
        data = report.to_dict()
        assert data["workflow_id"] == "wf-123"
        assert data["status"] == "completed"
        assert "src/auth.py" in data["files_created"]
        assert data["tests_passed"] == 5

    def test_report_with_commit_info(self):
        """Report includes commit info if available."""
        report = ArtifactReport(
            workflow_id="wf-123",
            task="Fix bug",
            status="completed",
            commit_sha="abc123",
            pr_url="https://github.com/org/repo/pull/1",
        )
        data = report.to_dict()
        assert data["commit_sha"] == "abc123"
        assert data["pr_url"] == "https://github.com/org/repo/pull/1"


# =============================================================================
# Decision Flow Tests
# =============================================================================

class TestDecisionFlow:
    """Test the multi-step decision flow."""

    @pytest.fixture
    def policy(self):
        return DeliveryLoopPolicy(max_fix_cycles=2, max_architect_cycles=1)

    def test_commit_decision_leads_to_pr_decision(self, policy):
        """After commit decision, PR decision is next."""
        ctx = policy.create_workflow("session-1", "Implement feature")
        ctx.state = WorkflowState.AWAITING_USER
        ctx.pending_decision = UserDecisionType.COMMIT

        # Mock devops result
        ctx.devops_result = DevOpsResult(
            options_presented=["commit", "pr"],
            commit_message="feat: add feature",
        )

        # User says yes to commit
        decision = UserDecisionResponse(
            decision_type=UserDecisionType.COMMIT,
            approved=True,
            value="feat: add feature",
        )
        policy.resume_after_user_decision(ctx.workflow_id, decision)

        assert ctx.user_wants_commit is True
        assert ctx.commit_message == "feat: add feature"
        assert ctx.pending_decision == UserDecisionType.PR

    def test_pr_decision_leads_to_deploy_if_available(self, policy):
        """After PR decision, deploy decision is next if available."""
        ctx = policy.create_workflow("session-1", "Implement feature")
        ctx.state = WorkflowState.AWAITING_USER
        ctx.pending_decision = UserDecisionType.PR
        ctx.user_wants_commit = True

        # Mock devops result with deploy available
        ctx.devops_result = DevOpsResult(
            options_presented=["commit", "pr", "deploy"],
            deploy_available=True,
            deploy_environments=["staging"],
        )

        decision = UserDecisionResponse(
            decision_type=UserDecisionType.PR,
            approved=True,
        )
        policy.resume_after_user_decision(ctx.workflow_id, decision)

        assert ctx.user_wants_pr is True
        assert ctx.pending_decision == UserDecisionType.DEPLOY

    def test_pr_decision_leads_to_docs_if_no_deploy(self, policy):
        """After PR decision, docs is next if no deploy available."""
        ctx = policy.create_workflow("session-1", "Implement feature")
        ctx.state = WorkflowState.AWAITING_USER
        ctx.pending_decision = UserDecisionType.PR
        ctx.user_wants_commit = True

        # Mock devops result without deploy
        ctx.devops_result = DevOpsResult(
            options_presented=["commit", "pr"],
            deploy_available=False,
        )

        decision = UserDecisionResponse(
            decision_type=UserDecisionType.PR,
            approved=False,
        )
        policy.resume_after_user_decision(ctx.workflow_id, decision)

        assert ctx.user_wants_pr is False
        assert ctx.pending_decision == UserDecisionType.DOCS

    def test_docs_decision_yes_transitions_to_documenting(self, policy):
        """Docs yes transitions to DOCUMENTING state."""
        ctx = policy.create_workflow("session-1", "Implement feature")
        ctx.state = WorkflowState.AWAITING_USER
        ctx.pending_decision = UserDecisionType.DOCS

        decision = UserDecisionResponse(
            decision_type=UserDecisionType.DOCS,
            approved=True,
        )
        policy.resume_after_user_decision(ctx.workflow_id, decision)

        assert ctx.user_wants_docs is True
        assert ctx.state == WorkflowState.DOCUMENTING
        assert ctx.pending_decision is None

    def test_docs_decision_no_transitions_to_completed(self, policy):
        """Docs no transitions to COMPLETED state."""
        ctx = policy.create_workflow("session-1", "Implement feature")
        ctx.state = WorkflowState.AWAITING_USER
        ctx.pending_decision = UserDecisionType.DOCS

        decision = UserDecisionResponse(
            decision_type=UserDecisionType.DOCS,
            approved=False,
        )
        policy.resume_after_user_decision(ctx.workflow_id, decision)

        assert ctx.user_wants_docs is False
        assert ctx.state == WorkflowState.COMPLETED
        assert ctx.pending_decision is None

    def test_declining_commit_skips_to_docs(self, policy):
        """Declining commit goes directly to docs question."""
        ctx = policy.create_workflow("session-1", "Implement feature")
        ctx.state = WorkflowState.AWAITING_USER
        ctx.pending_decision = UserDecisionType.COMMIT

        ctx.devops_result = DevOpsResult(options_presented=["commit", "pr", "deploy"])

        decision = UserDecisionResponse(
            decision_type=UserDecisionType.COMMIT,
            approved=False,
        )
        policy.resume_after_user_decision(ctx.workflow_id, decision)

        assert ctx.user_wants_commit is False
        assert ctx.pending_decision == UserDecisionType.DOCS


# =============================================================================
# Get Next Decision Tests
# =============================================================================

class TestGetNextDecision:
    """Test getting the next decision to present."""

    @pytest.fixture
    def policy(self):
        return DeliveryLoopPolicy()

    def test_get_commit_decision(self, policy):
        """Get commit decision with context."""
        ctx = policy.create_workflow("session-1", "Implement feature")
        ctx.pending_decision = UserDecisionType.COMMIT
        ctx.devops_result = DevOpsResult(
            commit_message="feat: add feature",
            branch_name="feature/add-feature",
            files_changed=["src/main.py"],
        )

        decision = policy.get_next_decision(ctx)
        assert decision is not None
        assert decision.decision_type == UserDecisionType.COMMIT
        assert "commit" in decision.question.lower()
        assert decision.context["suggested_message"] == "feat: add feature"
        assert decision.context["suggested_branch"] == "feature/add-feature"

    def test_get_pr_decision(self, policy):
        """Get PR decision."""
        ctx = policy.create_workflow("session-1", "Implement feature")
        ctx.pending_decision = UserDecisionType.PR

        decision = policy.get_next_decision(ctx)
        assert decision is not None
        assert decision.decision_type == UserDecisionType.PR
        assert "pull request" in decision.question.lower()
        assert decision.required is False

    def test_get_deploy_decision(self, policy):
        """Get deploy decision with environments."""
        ctx = policy.create_workflow("session-1", "Implement feature")
        ctx.pending_decision = UserDecisionType.DEPLOY
        ctx.devops_result = DevOpsResult(
            deploy_environments=["staging", "production"],
        )

        decision = policy.get_next_decision(ctx)
        assert decision is not None
        assert decision.decision_type == UserDecisionType.DEPLOY
        assert "deploy" in decision.question.lower()
        assert "staging" in decision.context["environments"]

    def test_no_decision_when_none_pending(self, policy):
        """No decision returned when nothing pending."""
        ctx = policy.create_workflow("session-1", "Implement feature")
        ctx.pending_decision = None

        decision = policy.get_next_decision(ctx)
        assert decision is None


# =============================================================================
# SSE Event Tests
# =============================================================================

class TestGateSSEEvents:
    """Test SSE events emitted during gate decisions."""

    @pytest.fixture
    def policy(self):
        return DeliveryLoopPolicy(max_fix_cycles=2, max_architect_cycles=1)

    @pytest.mark.asyncio
    async def test_devops_emits_user_decision_event(self, policy):
        """DevOps emits user_decision_requested event."""
        events = []

        async def mock_spawn(agent_id, prompt, context):
            if agent_id == "coder":
                return "Implemented. Created file: main.py"
            elif agent_id == "tester":
                return "All tests passed. OK (5 tests)"
            elif agent_id == "devops":
                return """
                ## Changes Summary
                Added authentication feature

                ## Suggested Commit
                - **Message:** "feat: add auth"
                - **Branch:** "feature/auth"

                ## Deployment Options
                - Commit only
                """
            return ""

        async for event in policy.run(
            session_id="test",
            task="Implement feature",
            spawn_agent_fn=mock_spawn,
        ):
            events.append(event)

        # Find user_decision_requested event
        decision_events = [e for e in events if e.type == "user_decision_requested"]
        assert len(decision_events) >= 1

        commit_decision = decision_events[0]
        assert commit_decision.data["decision_type"] == "commit"
        assert "question" in commit_decision.data

    @pytest.mark.asyncio
    async def test_devops_emits_artifact_report_event(self, policy):
        """DevOps emits artifact_report event."""
        events = []

        async def mock_spawn(agent_id, prompt, context):
            if agent_id == "coder":
                return "Implemented. Created file: main.py"
            elif agent_id == "tester":
                return "All tests passed. OK (5 tests)"
            elif agent_id == "devops":
                return """
                ## Files Changed
                - modified: main.py

                ## Suggested Commit
                - **Message:** "feat: add feature"
                """
            return ""

        async for event in policy.run(
            session_id="test",
            task="Implement feature",
            spawn_agent_fn=mock_spawn,
        ):
            events.append(event)

        # Find artifact_report event
        report_events = [e for e in events if e.type == "artifact_report"]
        assert len(report_events) == 1

        report = report_events[0]
        assert report.data["workflow_id"].startswith("wf-")
        assert "status" in report.data


# =============================================================================
# Artifact Report Build Tests
# =============================================================================

class TestArtifactReportBuild:
    """Test building artifact report from workflow context."""

    @pytest.fixture
    def policy(self):
        return DeliveryLoopPolicy()

    def test_build_report_with_coder_artifacts(self, policy):
        """Report includes coder artifacts."""
        ctx = policy.create_workflow("session-1", "Implement feature")

        # Mock coder result
        from app.workflows.delivery_loop import CoderResult
        ctx.coder_result = CoderResult(
            status=AgentOutcome.DONE,
            artifacts=["src/auth.py", "src/utils.py"],
            summary="Implemented authentication",
        )

        report = policy._build_artifact_report(ctx)
        assert "src/auth.py" in report.files_modified
        assert "src/utils.py" in report.files_modified

    def test_build_report_with_tester_stats(self, policy):
        """Report includes tester statistics."""
        ctx = policy.create_workflow("session-1", "Implement feature")

        # Mock tester result
        from app.workflows.delivery_loop import TesterResult
        ctx.tester_result = TesterResult(
            status=AgentOutcome.PASS,
            tests_run=10,
            tests_passed=10,
            tests_failed=0,
        )

        report = policy._build_artifact_report(ctx)
        assert report.tests_run == 10
        assert report.tests_passed == 10

    def test_build_report_status_reflects_workflow_state(self, policy):
        """Report status reflects workflow state."""
        ctx = policy.create_workflow("session-1", "Implement feature")
        ctx.state = WorkflowState.COMPLETED

        report = policy._build_artifact_report(ctx)
        assert report.status == "completed"

        ctx.state = WorkflowState.FAILED
        report = policy._build_artifact_report(ctx)
        assert report.status == "failed"


# =============================================================================
# Declining All Options Tests
# =============================================================================

class TestDecliningAllOptions:
    """Test that declining all options still produces a report."""

    @pytest.fixture
    def policy(self):
        return DeliveryLoopPolicy()

    def test_declining_commit_still_produces_report(self, policy):
        """Declining commit still produces artifact report."""
        ctx = policy.create_workflow("session-1", "Implement feature")
        ctx.state = WorkflowState.AWAITING_USER
        ctx.pending_decision = UserDecisionType.COMMIT

        # Mock results
        from app.workflows.delivery_loop import CoderResult, TesterResult
        ctx.coder_result = CoderResult(
            status=AgentOutcome.DONE,
            artifacts=["src/main.py"],
        )
        ctx.tester_result = TesterResult(
            status=AgentOutcome.PASS,
            tests_run=5,
            tests_passed=5,
        )
        ctx.devops_result = DevOpsResult(options_presented=["commit"])

        # Build artifact report before any decisions
        report = policy._build_artifact_report(ctx)
        assert report.status == "completed"
        assert "src/main.py" in report.files_modified
        assert report.tests_passed == 5

    def test_full_decline_flow_reaches_completed(self, policy):
        """Declining all options reaches COMPLETED state with report."""
        ctx = policy.create_workflow("session-1", "Implement feature")
        ctx.state = WorkflowState.AWAITING_USER
        ctx.pending_decision = UserDecisionType.COMMIT
        ctx.devops_result = DevOpsResult(
            options_presented=["commit", "pr"],
            deploy_available=False,
        )

        # Decline commit
        policy.resume_after_user_decision(
            ctx.workflow_id,
            UserDecisionResponse(decision_type=UserDecisionType.COMMIT, approved=False)
        )
        assert ctx.pending_decision == UserDecisionType.DOCS

        # Decline docs
        policy.resume_after_user_decision(
            ctx.workflow_id,
            UserDecisionResponse(decision_type=UserDecisionType.DOCS, approved=False)
        )

        assert ctx.state == WorkflowState.COMPLETED
        assert ctx.user_wants_commit is False
        assert ctx.user_wants_docs is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
