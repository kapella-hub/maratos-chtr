"""Tests for the error recovery system."""

import asyncio
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, patch

from app.subagents.recovery import (
    FailureContext,
    FailureLogger,
    FailureType,
    RecoveryAction,
    RecoveryConfig,
    RecoveryStrategy,
    classify_error,
    determine_recovery_action,
    execute_with_retry,
    execute_with_timeout,
    failure_logger,
    FALLBACK_AGENTS,
)


class TestFailureType:
    """Test FailureType enum."""

    def test_failure_types_exist(self):
        """Verify all failure types are defined."""
        assert FailureType.TIMEOUT == "timeout"
        assert FailureType.AGENT_ERROR == "agent_error"
        assert FailureType.MEMORY_ERROR == "memory_error"
        assert FailureType.TOOL_ERROR == "tool_error"
        assert FailureType.API_ERROR == "api_error"
        assert FailureType.UNKNOWN == "unknown"


class TestRecoveryStrategy:
    """Test RecoveryStrategy enum."""

    def test_strategies_exist(self):
        """Verify all recovery strategies are defined."""
        assert RecoveryStrategy.RETRY == "retry"
        assert RecoveryStrategy.FALLBACK_AGENT == "fallback_agent"
        assert RecoveryStrategy.DIAGNOSE == "diagnose"
        assert RecoveryStrategy.ESCALATE == "escalate"
        assert RecoveryStrategy.ABORT == "abort"


class TestClassifyError:
    """Test error classification."""

    def test_timeout_errors(self):
        """Test timeout error classification."""
        failure_type, strategy = classify_error("Task timed out after 300s")
        assert failure_type == FailureType.TIMEOUT
        assert strategy == RecoveryStrategy.RETRY

        failure_type, strategy = classify_error("Connection timeout")
        assert failure_type == FailureType.TIMEOUT
        assert strategy == RecoveryStrategy.RETRY

    def test_api_errors(self):
        """Test API error classification."""
        failure_type, strategy = classify_error("Rate limit exceeded (429)")
        assert failure_type == FailureType.API_ERROR
        assert strategy == RecoveryStrategy.RETRY

        failure_type, strategy = classify_error("rate_limit_error")
        assert failure_type == FailureType.API_ERROR
        assert strategy == RecoveryStrategy.RETRY

        failure_type, strategy = classify_error("Network connection failed")
        assert failure_type == FailureType.API_ERROR
        assert strategy == RecoveryStrategy.RETRY

    def test_tool_errors(self):
        """Test tool error classification."""
        failure_type, strategy = classify_error("File not found: /path/to/file")
        assert failure_type == FailureType.TOOL_ERROR
        assert strategy == RecoveryStrategy.DIAGNOSE

        failure_type, strategy = classify_error("Permission denied")
        assert failure_type == FailureType.TOOL_ERROR
        assert strategy == RecoveryStrategy.DIAGNOSE

    def test_agent_errors(self):
        """Test agent error classification."""
        failure_type, strategy = classify_error("Syntax error in generated code")
        assert failure_type == FailureType.AGENT_ERROR
        assert strategy == RecoveryStrategy.FALLBACK_AGENT

        failure_type, strategy = classify_error("Test failed: assertion error")
        assert failure_type == FailureType.AGENT_ERROR
        assert strategy == RecoveryStrategy.FALLBACK_AGENT

    def test_unknown_errors(self):
        """Test unknown error classification."""
        failure_type, strategy = classify_error("Some random error")
        assert failure_type == FailureType.UNKNOWN
        assert strategy == RecoveryStrategy.RETRY


class TestFailureContext:
    """Test FailureContext dataclass."""

    def create_failure(self, **kwargs) -> FailureContext:
        """Create a failure context with defaults."""
        defaults = {
            "task_id": "test-123",
            "agent_id": "coder",
            "task_description": "Test task",
            "failure_type": FailureType.AGENT_ERROR,
            "error_message": "Test error",
            "attempt": 1,
            "max_attempts": 3,
            "started_at": datetime.now(),
            "failed_at": datetime.now(),
            "duration_seconds": 1.5,
        }
        defaults.update(kwargs)
        return FailureContext(**defaults)

    def test_to_dict(self):
        """Test conversion to dictionary."""
        failure = self.create_failure()
        result = failure.to_dict()

        assert result["task_id"] == "test-123"
        assert result["agent_id"] == "coder"
        assert result["failure_type"] == "agent_error"
        assert result["attempt"] == 1
        assert result["max_attempts"] == 3

    def test_to_dict_truncates_description(self):
        """Test that long descriptions are truncated."""
        failure = self.create_failure(task_description="x" * 500)
        result = failure.to_dict()

        assert len(result["task_description"]) == 200


class TestFailureLogger:
    """Test FailureLogger class."""

    def test_log_failure(self):
        """Test logging a failure."""
        logger = FailureLogger(max_history=10)
        failure = FailureContext(
            task_id="test-1",
            agent_id="coder",
            task_description="Test",
            failure_type=FailureType.AGENT_ERROR,
            error_message="Error",
            attempt=1,
            max_attempts=3,
            started_at=datetime.now(),
            failed_at=datetime.now(),
            duration_seconds=1.0,
        )

        logger.log_failure(failure)
        recent = logger.get_recent_failures(limit=10)

        assert len(recent) == 1
        assert recent[0].task_id == "test-1"

    def test_max_history_limit(self):
        """Test that history is limited."""
        logger = FailureLogger(max_history=5)

        for i in range(10):
            failure = FailureContext(
                task_id=f"test-{i}",
                agent_id="coder",
                task_description="Test",
                failure_type=FailureType.AGENT_ERROR,
                error_message="Error",
                attempt=1,
                max_attempts=3,
                started_at=datetime.now(),
                failed_at=datetime.now(),
                duration_seconds=1.0,
            )
            logger.log_failure(failure)

        recent = logger.get_recent_failures(limit=100)
        assert len(recent) == 5

    def test_filter_by_agent(self):
        """Test filtering failures by agent."""
        logger = FailureLogger()

        for agent in ["coder", "coder", "reviewer"]:
            failure = FailureContext(
                task_id=f"test-{agent}",
                agent_id=agent,
                task_description="Test",
                failure_type=FailureType.AGENT_ERROR,
                error_message="Error",
                attempt=1,
                max_attempts=3,
                started_at=datetime.now(),
                failed_at=datetime.now(),
                duration_seconds=1.0,
            )
            logger.log_failure(failure)

        coder_failures = logger.get_recent_failures(agent_id="coder")
        assert len(coder_failures) == 2

        reviewer_failures = logger.get_recent_failures(agent_id="reviewer")
        assert len(reviewer_failures) == 1

    def test_failure_stats(self):
        """Test failure statistics."""
        logger = FailureLogger()

        for i, (agent, ftype) in enumerate([
            ("coder", FailureType.AGENT_ERROR),
            ("coder", FailureType.TIMEOUT),
            ("reviewer", FailureType.AGENT_ERROR),
        ]):
            failure = FailureContext(
                task_id=f"test-{i}",
                agent_id=agent,
                task_description="Test",
                failure_type=ftype,
                error_message="Error",
                attempt=1,
                max_attempts=3,
                started_at=datetime.now(),
                failed_at=datetime.now(),
                duration_seconds=1.0,
            )
            logger.log_failure(failure)

        stats = logger.get_failure_stats()
        assert stats["total"] == 3
        assert stats["by_agent"]["coder"] == 2
        assert stats["by_agent"]["reviewer"] == 1
        assert stats["by_type"]["agent_error"] == 2
        assert stats["by_type"]["timeout"] == 1


class TestDetermineRecoveryAction:
    """Test recovery action determination."""

    def create_failure(self, **kwargs) -> FailureContext:
        """Create a failure context with defaults."""
        defaults = {
            "task_id": "test-123",
            "agent_id": "coder",
            "task_description": "Test task",
            "failure_type": FailureType.AGENT_ERROR,
            "error_message": "Test error",
            "attempt": 1,
            "max_attempts": 3,
            "started_at": datetime.now(),
            "failed_at": datetime.now(),
            "duration_seconds": 1.5,
        }
        defaults.update(kwargs)
        return FailureContext(**defaults)

    def test_retry_on_first_attempt(self):
        """Test that first attempt failures retry."""
        failure = self.create_failure(
            error_message="Rate limit exceeded",
            attempt=1,
        )
        action = determine_recovery_action(failure)

        assert action.strategy == RecoveryStrategy.RETRY
        assert action.delay_seconds > 0

    def test_exponential_backoff(self):
        """Test exponential backoff on retries."""
        config = RecoveryConfig(base_delay_seconds=2.0)

        failure1 = self.create_failure(attempt=1, error_message="timeout")
        action1 = determine_recovery_action(failure1, config)

        failure2 = self.create_failure(attempt=2, error_message="timeout")
        action2 = determine_recovery_action(failure2, config)

        assert action2.delay_seconds > action1.delay_seconds

    def test_fallback_after_max_retries(self):
        """Test fallback agent is suggested after max retries."""
        config = RecoveryConfig(max_retries=3, enable_fallback=True)
        failure = self.create_failure(
            agent_id="coder",
            attempt=3,  # Max retries exhausted
            error_message="syntax error",  # Non-retriable
        )

        action = determine_recovery_action(failure, config)

        assert action.strategy == RecoveryStrategy.FALLBACK_AGENT
        assert action.agent_id == "reviewer"  # First fallback for coder

    def test_abort_when_no_recovery(self):
        """Test abort when no recovery is possible."""
        config = RecoveryConfig(
            max_retries=1,
            enable_fallback=False,
            enable_diagnosis=False,
        )
        failure = self.create_failure(
            agent_id="unknown_agent",
            attempt=1,
            error_message="permanent error",
        )

        action = determine_recovery_action(failure, config)

        assert action.strategy == RecoveryStrategy.ABORT


class TestFallbackAgents:
    """Test fallback agent mappings."""

    def test_coder_fallbacks(self):
        """Test coder fallback agents."""
        assert "reviewer" in FALLBACK_AGENTS["coder"]
        assert "architect" in FALLBACK_AGENTS["coder"]

    def test_tester_fallbacks(self):
        """Test tester fallback agents."""
        assert "coder" in FALLBACK_AGENTS["tester"]
        assert "reviewer" in FALLBACK_AGENTS["tester"]

    def test_all_agents_have_fallbacks(self):
        """Test all major agents have fallbacks defined."""
        expected_agents = ["coder", "tester", "reviewer", "architect", "docs", "devops"]
        for agent in expected_agents:
            assert agent in FALLBACK_AGENTS
            assert len(FALLBACK_AGENTS[agent]) > 0


class TestExecuteWithRetry:
    """Test execute_with_retry function."""

    @pytest.mark.asyncio
    async def test_success_on_first_try(self):
        """Test successful execution on first try."""
        async def work_fn():
            return "success"

        result, failures = await execute_with_retry(
            work_fn=work_fn,
            task_id="test-1",
            agent_id="coder",
            task_description="Test task",
        )

        assert result == "success"
        assert len(failures) == 0

    @pytest.mark.asyncio
    async def test_retry_on_failure(self):
        """Test retry on transient failure."""
        attempt_count = 0

        async def work_fn():
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 2:
                raise Exception("timeout error")
            return "success"

        config = RecoveryConfig(max_retries=3, base_delay_seconds=0.01)
        result, failures = await execute_with_retry(
            work_fn=work_fn,
            task_id="test-1",
            agent_id="coder",
            task_description="Test task",
            config=config,
        )

        assert result == "success"
        assert len(failures) == 1
        assert attempt_count == 2

    @pytest.mark.asyncio
    async def test_max_retries_exceeded(self):
        """Test failure after max retries."""
        async def work_fn():
            raise Exception("persistent error")

        config = RecoveryConfig(max_retries=2, base_delay_seconds=0.01)

        with pytest.raises(Exception) as exc_info:
            await execute_with_retry(
                work_fn=work_fn,
                task_id="test-1",
                agent_id="coder",
                task_description="Test task",
                config=config,
            )

        assert "persistent error" in str(exc_info.value)


class TestExecuteWithTimeout:
    """Test execute_with_timeout function."""

    @pytest.mark.asyncio
    async def test_completes_within_timeout(self):
        """Test task completes within timeout."""
        async def work_fn():
            await asyncio.sleep(0.01)
            return "done"

        result = await execute_with_timeout(work_fn, timeout_seconds=1.0)
        assert result == "done"

    @pytest.mark.asyncio
    async def test_timeout_exceeded(self):
        """Test timeout is raised when exceeded."""
        async def work_fn():
            await asyncio.sleep(10)
            return "done"

        with pytest.raises(asyncio.TimeoutError):
            await execute_with_timeout(work_fn, timeout_seconds=0.01)


class TestRecoveryConfig:
    """Test RecoveryConfig class."""

    def test_default_values(self):
        """Test default configuration values."""
        config = RecoveryConfig()

        assert config.max_retries == 3
        assert config.base_delay_seconds == 2.0
        assert config.max_delay_seconds == 30.0
        assert config.timeout_seconds == 300.0
        assert config.enable_fallback is True
        assert config.enable_diagnosis is True

    def test_custom_values(self):
        """Test custom configuration values."""
        config = RecoveryConfig(
            max_retries=5,
            base_delay_seconds=1.0,
            timeout_seconds=600.0,
            enable_fallback=False,
        )

        assert config.max_retries == 5
        assert config.base_delay_seconds == 1.0
        assert config.timeout_seconds == 600.0
        assert config.enable_fallback is False
