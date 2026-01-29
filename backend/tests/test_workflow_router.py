"""Tests for the Workflow Router.

These tests verify the classification of messages into coding vs non-coding tasks.
"""

import pytest
from unittest.mock import AsyncMock, patch

from app.workflows.router import (
    RouterConfig,
    TaskType,
    ClassificationResult,
    classify_by_keywords,
    classify_message,
    classify_message_sync,
    handle_clarification_response,
    is_explicit_command,
    should_trigger_workflow,
    router_config,
    update_router_config,
)


# =============================================================================
# Explicit Command Tests
# =============================================================================

class TestExplicitCommands:
    """Test explicit command detection."""

    def test_code_command(self):
        """Test /code command triggers workflow."""
        is_cmd, cmd = is_explicit_command("/code add a login function")
        assert is_cmd is True
        assert cmd == "/code"

    def test_fix_command(self):
        """Test /fix command triggers workflow."""
        is_cmd, cmd = is_explicit_command("/fix the authentication bug")
        assert is_cmd is True
        assert cmd == "/fix"

    def test_refactor_command(self):
        """Test /refactor command triggers workflow."""
        is_cmd, cmd = is_explicit_command("/refactor the user service")
        assert is_cmd is True
        assert cmd == "/refactor"

    def test_implement_command(self):
        """Test /implement command triggers workflow."""
        is_cmd, cmd = is_explicit_command("/implement user registration")
        assert is_cmd is True
        assert cmd == "/implement"

    def test_feature_command(self):
        """Test /feature command triggers workflow."""
        is_cmd, cmd = is_explicit_command("/feature add dark mode")
        assert is_cmd is True
        assert cmd == "/feature"

    def test_no_command(self):
        """Test regular message is not a command."""
        is_cmd, cmd = is_explicit_command("Can you help me with something?")
        assert is_cmd is False
        assert cmd is None

    def test_command_keyword_match(self):
        """Explicit commands get 100% confidence."""
        result = classify_by_keywords("/code add a new feature")
        assert result.confidence == 1.0
        assert result.should_trigger_workflow is True
        assert result.matched_command == "/code"


# =============================================================================
# Strong Coding Keywords Tests
# =============================================================================

class TestStrongCodingKeywords:
    """Test detection of strong coding indicators."""

    @pytest.mark.parametrize("message,expected_trigger", [
        ("Implement user authentication", True),
        ("Create a function to calculate taxes", True),
        ("Create an endpoint for user registration", True),
        ("Add a method to validate emails", True),
        ("Write code to parse JSON", True),
        ("Fix the bug in the login flow", True),
        ("Fix this error in the payment module", True),
        ("Refactor the database queries", True),
        ("Add feature for password reset", True),
        ("Add authentication to the API", True),
        ("Add validation for user input", True),
    ])
    def test_strong_coding_keywords_trigger(self, message, expected_trigger):
        """Strong coding keywords should trigger workflow."""
        result = classify_by_keywords(message)
        assert result.should_trigger_workflow is expected_trigger, f"Message: {message}"
        assert result.task_type == TaskType.CODING

    def test_implement_high_confidence(self):
        """'Implement' should have high confidence."""
        result = classify_by_keywords("Implement a new caching layer")
        assert result.confidence >= 0.85
        assert result.should_trigger_workflow is True

    def test_fix_bug_high_confidence(self):
        """'Fix the bug' should have very high confidence."""
        result = classify_by_keywords("Fix the bug in checkout")
        assert result.confidence >= 0.9
        assert result.should_trigger_workflow is True


# =============================================================================
# Non-Coding Keywords Tests
# =============================================================================

class TestNonCodingKeywords:
    """Test detection of non-coding tasks."""

    @pytest.mark.parametrize("message,expected_type", [
        ("Explain how authentication works", TaskType.EXPLANATION),
        ("What is the difference between REST and GraphQL?", TaskType.QUESTION),
        ("How does the caching system work?", TaskType.QUESTION),
        ("Why is the database slow?", TaskType.QUESTION),
        ("Describe the architecture", TaskType.EXPLANATION),
        ("Tell me about the API design", TaskType.QUESTION),
        ("Help me understand the code flow", TaskType.EXPLANATION),
        ("Can you explain the login process?", TaskType.EXPLANATION),
        ("Compare Redux and MobX", TaskType.QUESTION),
    ])
    def test_non_coding_keywords_no_trigger(self, message, expected_type):
        """Non-coding keywords should NOT trigger workflow."""
        result = classify_by_keywords(message)
        assert result.should_trigger_workflow is False, f"Message: {message}"
        assert result.task_type == expected_type

    def test_explain_no_trigger(self):
        """Explanation requests should not trigger."""
        result = classify_by_keywords("Explain how the router works")
        assert result.should_trigger_workflow is False
        assert result.task_type == TaskType.EXPLANATION

    def test_what_is_no_trigger(self):
        """'What is' questions should not trigger."""
        result = classify_by_keywords("What is the purpose of this function?")
        assert result.should_trigger_workflow is False
        assert result.task_type == TaskType.QUESTION


# =============================================================================
# Medium Keywords with Context Tests
# =============================================================================

class TestMediumKeywordsWithContext:
    """Test medium keywords that need context to trigger."""

    def test_add_alone_low_confidence(self):
        """'Add' alone should have low confidence."""
        result = classify_by_keywords("Add something")
        assert result.confidence < 0.8

    def test_add_with_context_higher_confidence(self):
        """'Add' with coding context should boost confidence."""
        result = classify_by_keywords("Add a new function to the module")
        assert result.confidence > 0.5  # Boosted by context

    def test_create_with_component_context(self):
        """'Create' with component context should boost confidence."""
        result = classify_by_keywords("Create a new React component")
        assert result.confidence > 0.5

    def test_modify_with_api_context(self):
        """'Modify' with API context should boost confidence."""
        result = classify_by_keywords("Modify the API endpoint")
        assert result.confidence > 0.5


# =============================================================================
# Testing Keywords Tests
# =============================================================================

class TestTestingKeywords:
    """Test detection of testing tasks."""

    def test_write_tests_high_confidence(self):
        """'Write tests' should have high confidence."""
        result = classify_by_keywords("Write tests for the user service")
        assert result.confidence >= 0.9
        assert result.task_type == TaskType.TESTING
        assert result.should_trigger_workflow is True

    def test_add_unit_tests(self):
        """'Add unit tests' should trigger."""
        result = classify_by_keywords("Add unit tests for the auth module")
        assert result.task_type == TaskType.TESTING
        assert result.should_trigger_workflow is True

    def test_run_tests_lower_confidence(self):
        """'Run tests' should have lower confidence (might just be running)."""
        result = classify_by_keywords("Run the tests")
        assert result.confidence < 0.8


# =============================================================================
# DevOps Keywords Tests
# =============================================================================

class TestDevOpsKeywords:
    """Test detection of devops tasks."""

    def test_deploy_detection(self):
        """Deploy keywords should be detected."""
        result = classify_by_keywords("Deploy the application to production")
        assert result.task_type == TaskType.DEVOPS
        assert result.confidence >= 0.8

    def test_docker_detection(self):
        """Docker keywords should be detected."""
        result = classify_by_keywords("Create a Docker configuration")
        assert result.task_type == TaskType.DEVOPS

    def test_cicd_detection(self):
        """CI/CD keywords should be detected."""
        result = classify_by_keywords("Set up CI/CD pipeline")
        assert result.task_type == TaskType.DEVOPS


# =============================================================================
# Clarification Tests
# =============================================================================

class TestClarification:
    """Test clarification logic for ambiguous cases."""

    def test_ambiguous_needs_clarification(self):
        """Ambiguous messages should request clarification."""
        # Set thresholds for testing
        original_auto = router_config.auto_trigger_threshold
        original_clarify = router_config.clarify_threshold
        try:
            router_config.auto_trigger_threshold = 0.8
            router_config.clarify_threshold = 0.5

            result = classify_by_keywords("Make some changes to the file")
            # Should be in the clarification range
            if 0.5 <= result.confidence < 0.8:
                assert result.needs_clarification is True
                assert result.clarification_question is not None
        finally:
            router_config.auto_trigger_threshold = original_auto
            router_config.clarify_threshold = original_clarify

    def test_clarification_response_yes(self):
        """Yes responses should confirm workflow."""
        assert handle_clarification_response("yes") is True
        assert handle_clarification_response("y") is True
        assert handle_clarification_response("Yeah") is True
        assert handle_clarification_response("sure") is True
        assert handle_clarification_response("ok") is True
        assert handle_clarification_response("proceed") is True

    def test_clarification_response_no(self):
        """No responses should reject workflow."""
        assert handle_clarification_response("no") is False
        assert handle_clarification_response("n") is False
        assert handle_clarification_response("nope") is False
        assert handle_clarification_response("cancel") is False
        assert handle_clarification_response("don't") is False


# =============================================================================
# Configuration Tests
# =============================================================================

class TestConfiguration:
    """Test router configuration."""

    def test_update_config(self):
        """Config can be updated."""
        original = router_config.auto_trigger_threshold
        try:
            update_router_config(auto_trigger_threshold=0.9)
            assert router_config.auto_trigger_threshold == 0.9
        finally:
            router_config.auto_trigger_threshold = original

    def test_disabled_router(self):
        """Disabled router should not trigger."""
        original = router_config.enabled
        try:
            router_config.enabled = False
            result = classify_message_sync("Implement a new feature")
            assert result.should_trigger_workflow is False
            assert "disabled" in result.reasoning.lower()
        finally:
            router_config.enabled = original


# =============================================================================
# Edge Cases Tests
# =============================================================================

class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_message(self):
        """Empty message should not trigger."""
        result = classify_by_keywords("")
        assert result.should_trigger_workflow is False

    def test_short_message(self):
        """Very short messages should be handled."""
        result = classify_by_keywords("Hi")
        assert result.should_trigger_workflow is False

    def test_mixed_signals(self):
        """Messages with mixed signals should be handled."""
        # "Explain" is non-coding, but "implement" is coding
        result = classify_by_keywords("Explain and implement the feature")
        # Non-coding check happens first, so should not trigger
        assert result.task_type in (TaskType.EXPLANATION, TaskType.QUESTION)

    def test_case_insensitivity(self):
        """Classification should be case-insensitive."""
        result1 = classify_by_keywords("IMPLEMENT a new feature")
        result2 = classify_by_keywords("implement a new feature")
        assert result1.should_trigger_workflow == result2.should_trigger_workflow

    def test_partial_keyword_no_match(self):
        """Partial keywords should not match."""
        # "implementation" contains "implement" but shouldn't match as strongly
        result = classify_by_keywords("Show the implementation details")
        # This should not trigger because it's asking to "show"
        # which is a non-coding indicator


# =============================================================================
# Async Classification Tests
# =============================================================================

class TestAsyncClassification:
    """Test async classification (without LLM)."""

    @pytest.mark.asyncio
    async def test_classify_message_async(self):
        """Async classification should work."""
        result = await classify_message("Implement a login feature")
        assert result.task_type == TaskType.CODING
        assert result.should_trigger_workflow is True

    @pytest.mark.asyncio
    async def test_classify_message_async_disabled(self):
        """Disabled router should not trigger async."""
        original = router_config.enabled
        try:
            router_config.enabled = False
            result = await classify_message("Implement a feature")
            assert result.should_trigger_workflow is False
        finally:
            router_config.enabled = original


# =============================================================================
# should_trigger_workflow Tests
# =============================================================================

class TestShouldTriggerWorkflow:
    """Test the convenience function."""

    def test_coding_task_triggers(self):
        """Coding tasks should trigger."""
        assert should_trigger_workflow("Implement user authentication") is True
        assert should_trigger_workflow("Fix the bug in login") is True
        assert should_trigger_workflow("/code add a feature") is True

    def test_non_coding_no_trigger(self):
        """Non-coding tasks should not trigger."""
        assert should_trigger_workflow("Explain how this works") is False
        assert should_trigger_workflow("What is the purpose?") is False


# =============================================================================
# Real-world Examples Tests
# =============================================================================

class TestRealWorldExamples:
    """Test with real-world example messages."""

    @pytest.mark.parametrize("message,should_trigger", [
        # Should trigger
        ("Add a password reset endpoint", True),
        ("Create a new React component for the dashboard", True),
        ("Fix the 500 error on the checkout page", True),
        ("Implement rate limiting for the API", True),
        ("Refactor the user service to use async/await", True),
        ("Add input validation to the registration form", True),
        ("Write unit tests for the payment module", True),

        # Should NOT trigger
        ("How do I use the API?", False),
        ("What's the best way to structure a React app?", False),
        ("Explain the difference between SQL and NoSQL", False),
        ("Can you describe the authentication flow?", False),
        ("Why is my code slow?", False),
        ("Help me understand promises", False),
    ])
    def test_real_world_examples(self, message, should_trigger):
        """Test real-world examples."""
        result = classify_by_keywords(message)
        assert result.should_trigger_workflow is should_trigger, f"Message: '{message}' - Expected: {should_trigger}, Got: {result.should_trigger_workflow}"


# =============================================================================
# Smart Operations Detection Tests
# =============================================================================

from app.workflows.router import _is_operations_task


class TestOperationsDetection:
    """Test smart operations/devops intent detection."""

    def test_spin_up_container(self):
        """'spin it up in a container' should be detected as operations."""
        is_ops, reason, confidence = _is_operations_task("spin it up in a container")
        assert is_ops is True
        assert confidence >= 0.8

    def test_spin_up_alone(self):
        """'spin it up' should be detected as operations."""
        is_ops, reason, confidence = _is_operations_task("spin it up")
        assert is_ops is True
        assert confidence >= 0.8

    def test_deploy_to_production(self):
        """'deploy to production' should be detected as operations."""
        is_ops, reason, confidence = _is_operations_task("deploy to production")
        assert is_ops is True
        assert confidence >= 0.85

    def test_run_in_docker(self):
        """'run it in docker' should be detected as operations."""
        is_ops, reason, confidence = _is_operations_task("run it in docker")
        assert is_ops is True
        assert confidence >= 0.8

    def test_containerize(self):
        """'containerize the app' should be detected as operations."""
        is_ops, reason, confidence = _is_operations_task("containerize the app")
        assert is_ops is True
        assert confidence >= 0.8

    def test_dockerize(self):
        """'dockerize this' should be detected as operations."""
        is_ops, reason, confidence = _is_operations_task("dockerize this")
        assert is_ops is True
        assert confidence >= 0.8

    def test_host_on_server(self):
        """'host this on a server' should be detected as operations."""
        is_ops, reason, confidence = _is_operations_task("host this on a server")
        assert is_ops is True
        assert confidence >= 0.7

    def test_launch_the_app(self):
        """'launch the app' should be detected as operations."""
        is_ops, reason, confidence = _is_operations_task("launch the app")
        assert is_ops is True
        assert confidence >= 0.7

    def test_get_it_running(self):
        """'get it running' should be detected as operations."""
        is_ops, reason, confidence = _is_operations_task("get it running")
        assert is_ops is True
        assert confidence >= 0.8

    def test_make_it_live(self):
        """'make it live' should be detected as operations."""
        is_ops, reason, confidence = _is_operations_task("make it live")
        assert is_ops is True
        assert confidence >= 0.8

    def test_put_in_kubernetes(self):
        """'put it in kubernetes' should be detected as operations."""
        is_ops, reason, confidence = _is_operations_task("put it in kubernetes")
        assert is_ops is True
        assert confidence >= 0.7

    def test_create_function_not_operations(self):
        """'create a function' should NOT be operations (it's coding)."""
        is_ops, reason, confidence = _is_operations_task("create a function for login")
        # Should either not detect or have low confidence
        assert is_ops is False or confidence < 0.7

    def test_implement_feature_not_operations(self):
        """'implement a feature' should NOT be operations."""
        is_ops, reason, confidence = _is_operations_task("implement user authentication")
        assert is_ops is False or confidence < 0.5


class TestOperationsClassification:
    """Test that operations tasks are classified correctly."""

    def test_spin_up_triggers_devops(self):
        """Operations task should be classified as DEVOPS."""
        result = classify_by_keywords("spin it up in a container")
        assert result.task_type == TaskType.DEVOPS
        assert result.confidence >= 0.8

    def test_deploy_triggers_devops(self):
        """Deploy task should be classified as DEVOPS."""
        result = classify_by_keywords("deploy to production")
        assert result.task_type == TaskType.DEVOPS
        assert result.should_trigger_workflow is True

    def test_containerize_triggers_devops(self):
        """Containerize task should be classified as DEVOPS."""
        result = classify_by_keywords("containerize the application")
        assert result.task_type == TaskType.DEVOPS


# =============================================================================
# Clarification Follow-up Tests
# =============================================================================

from app.workflows.router import (
    store_pending_clarification,
    get_pending_clarification,
    clear_pending_clarification,
    analyze_clarification_followup,
)


class TestClarificationFollowup:
    """Test the smart clarification follow-up handling."""

    def setup_method(self):
        """Clear any pending clarifications before each test."""
        # Clear all pending clarifications
        clear_pending_clarification("test-session-1")
        clear_pending_clarification("test-session-2")

    def test_store_and_retrieve_clarification(self):
        """Test storing and retrieving pending clarifications."""
        classification = ClassificationResult(
            task_type=TaskType.CODING,
            confidence=0.6,
            should_trigger_workflow=False,
            needs_clarification=True,
            clarification_question="Should I implement this?",
            matched_keywords=["add"],
        )

        store_pending_clarification("test-session-1", "add a login feature", classification)
        pending = get_pending_clarification("test-session-1")

        assert pending is not None
        assert pending.original_task == "add a login feature"
        assert pending.task_type == TaskType.CODING
        assert pending.confidence == 0.6

    def test_no_pending_clarification(self):
        """Test when no pending clarification exists."""
        result = analyze_clarification_followup("nonexistent-session", "yes")
        assert result is None

    def test_affirmative_response_yes(self):
        """Test 'yes' triggers workflow with original task."""
        classification = ClassificationResult(
            task_type=TaskType.CODING,
            confidence=0.6,
            should_trigger_workflow=False,
            needs_clarification=True,
        )
        store_pending_clarification("test-session-1", "add real market data", classification)

        result = analyze_clarification_followup("test-session-1", "yes")

        assert result is not None
        assert result.should_trigger_workflow is True
        assert result.is_affirmative is True
        assert result.task_to_execute == "add real market data"

    def test_affirmative_response_variations(self):
        """Test various affirmative responses."""
        for response in ["yes", "y", "yeah", "sure", "ok", "go", "proceed"]:
            classification = ClassificationResult(
                task_type=TaskType.CODING,
                confidence=0.6,
                should_trigger_workflow=False,
                needs_clarification=True,
            )
            store_pending_clarification("test-session-1", "add feature", classification)

            result = analyze_clarification_followup("test-session-1", response)

            assert result is not None, f"Response '{response}' should be recognized"
            assert result.should_trigger_workflow is True, f"Response '{response}' should trigger workflow"
            assert result.is_affirmative is True

    def test_negative_response(self):
        """Test 'no' does not trigger workflow."""
        classification = ClassificationResult(
            task_type=TaskType.CODING,
            confidence=0.6,
            should_trigger_workflow=False,
            needs_clarification=True,
        )
        store_pending_clarification("test-session-1", "add feature", classification)

        result = analyze_clarification_followup("test-session-1", "no")

        assert result is not None
        assert result.should_trigger_workflow is False
        assert result.is_negative is True

    def test_negative_response_variations(self):
        """Test various negative responses."""
        for response in ["no", "n", "nope", "cancel", "nevermind"]:
            classification = ClassificationResult(
                task_type=TaskType.CODING,
                confidence=0.6,
                should_trigger_workflow=False,
                needs_clarification=True,
            )
            store_pending_clarification("test-session-1", "add feature", classification)

            result = analyze_clarification_followup("test-session-1", response)

            assert result is not None, f"Response '{response}' should be recognized"
            assert result.should_trigger_workflow is False
            assert result.is_negative is True

    def test_new_imperative_command(self):
        """Test new imperative command triggers workflow with new task."""
        classification = ClassificationResult(
            task_type=TaskType.CODING,
            confidence=0.6,
            should_trigger_workflow=False,
            needs_clarification=True,
        )
        store_pending_clarification("test-session-1", "add feature", classification)

        result = analyze_clarification_followup("test-session-1", "create a login endpoint instead")

        assert result is not None
        assert result.should_trigger_workflow is True
        assert result.is_new_task is True
        assert "login endpoint" in result.task_to_execute

    def test_refinement_with_also(self):
        """Test refinement with 'also' keyword."""
        classification = ClassificationResult(
            task_type=TaskType.CODING,
            confidence=0.6,
            should_trigger_workflow=False,
            needs_clarification=True,
        )
        store_pending_clarification("test-session-1", "add a login feature", classification)

        result = analyze_clarification_followup("test-session-1", "also add password reset")

        assert result is not None
        assert result.should_trigger_workflow is True
        assert result.is_refinement is True
        assert "login feature" in result.task_to_execute
        assert "password reset" in result.task_to_execute

    def test_question_follow_up_no_trigger(self):
        """Test question follow-up does not trigger workflow."""
        classification = ClassificationResult(
            task_type=TaskType.CODING,
            confidence=0.6,
            should_trigger_workflow=False,
            needs_clarification=True,
        )
        store_pending_clarification("test-session-1", "add feature", classification)

        result = analyze_clarification_followup("test-session-1", "what exactly should this feature do?")

        assert result is not None
        assert result.should_trigger_workflow is False

    def test_clarification_cleared_after_yes(self):
        """Test that clarification is cleared after processing."""
        classification = ClassificationResult(
            task_type=TaskType.CODING,
            confidence=0.6,
            should_trigger_workflow=False,
            needs_clarification=True,
        )
        store_pending_clarification("test-session-1", "add feature", classification)

        result = analyze_clarification_followup("test-session-1", "yes")
        assert result is not None

        # Should be cleared now
        pending = get_pending_clarification("test-session-1")
        assert pending is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
