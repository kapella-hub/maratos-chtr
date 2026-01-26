"""Tests for API input validation."""

import pytest
from pydantic import ValidationError

from app.api.chat import ChatRequest
from app.api.subagents import SpawnTaskRequest, RunSkillRequest, ValidAgentId
from app.api.agents import AgentUpdate
from app.api.memory import RememberRequest, RecallRequest


class TestChatRequestValidation:
    """Tests for ChatRequest validation."""

    def test_valid_message(self):
        """Test that valid messages are accepted."""
        req = ChatRequest(message="Hello, how are you?")
        assert req.message == "Hello, how are you?"

    def test_empty_message_rejected(self):
        """Test that empty messages are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            ChatRequest(message="")
        assert "min_length" in str(exc_info.value).lower() or "at least 1" in str(exc_info.value).lower()

    def test_whitespace_only_message_rejected(self):
        """Test that whitespace-only messages are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            ChatRequest(message="   \n\t  ")
        assert "empty" in str(exc_info.value).lower() or "whitespace" in str(exc_info.value).lower()

    def test_long_message_rejected(self):
        """Test that extremely long messages are rejected."""
        with pytest.raises(ValidationError):
            ChatRequest(message="x" * 50001)

    def test_optional_fields(self):
        """Test optional fields work correctly."""
        req = ChatRequest(
            message="test",
            session_id="abc123",
            agent_id="mo",
            context={"key": "value"}
        )
        assert req.session_id == "abc123"
        assert req.agent_id == "mo"
        assert req.context == {"key": "value"}


class TestSpawnTaskRequestValidation:
    """Tests for SpawnTaskRequest validation."""

    def test_valid_request(self):
        """Test valid spawn request."""
        req = SpawnTaskRequest(task="Build a REST API")
        assert req.task == "Build a REST API"
        assert req.agent_id == ValidAgentId.MO

    def test_empty_task_rejected(self):
        """Test empty task is rejected."""
        with pytest.raises(ValidationError):
            SpawnTaskRequest(task="")

    def test_valid_agent_ids(self):
        """Test all valid agent IDs are accepted."""
        for agent in ValidAgentId:
            req = SpawnTaskRequest(task="test", agent_id=agent)
            assert req.agent_id == agent

    def test_invalid_agent_id_rejected(self):
        """Test invalid agent ID is rejected."""
        with pytest.raises(ValidationError):
            SpawnTaskRequest(task="test", agent_id="invalid_agent")


class TestAgentUpdateValidation:
    """Tests for AgentUpdate validation."""

    def test_valid_temperature(self):
        """Test valid temperature values."""
        for temp in [0.0, 0.5, 1.0, 1.5, 2.0]:
            req = AgentUpdate(temperature=temp)
            assert req.temperature == temp

    def test_temperature_below_zero_rejected(self):
        """Test temperature below 0 is rejected."""
        with pytest.raises(ValidationError):
            AgentUpdate(temperature=-0.1)

    def test_temperature_above_two_rejected(self):
        """Test temperature above 2 is rejected."""
        with pytest.raises(ValidationError):
            AgentUpdate(temperature=2.1)

    def test_empty_model_rejected(self):
        """Test empty model string is rejected."""
        with pytest.raises(ValidationError):
            AgentUpdate(model="")

    def test_valid_model(self):
        """Test valid model string."""
        req = AgentUpdate(model="claude-sonnet-4")
        assert req.model == "claude-sonnet-4"


class TestMemoryRequestValidation:
    """Tests for memory request validation."""

    def test_remember_valid(self):
        """Test valid remember request."""
        req = RememberRequest(content="Important fact to remember")
        assert req.content == "Important fact to remember"
        assert req.memory_type == "fact"
        assert req.importance == 0.5

    def test_remember_importance_bounds(self):
        """Test importance must be 0-1."""
        req = RememberRequest(content="test", importance=0.0)
        assert req.importance == 0.0

        req = RememberRequest(content="test", importance=1.0)
        assert req.importance == 1.0

        with pytest.raises(ValidationError):
            RememberRequest(content="test", importance=-0.1)

        with pytest.raises(ValidationError):
            RememberRequest(content="test", importance=1.1)

    def test_recall_limit_bounds(self):
        """Test recall limit must be 1-100."""
        req = RecallRequest(query="test", limit=1)
        assert req.limit == 1

        req = RecallRequest(query="test", limit=100)
        assert req.limit == 100

        with pytest.raises(ValidationError):
            RecallRequest(query="test", limit=0)

        with pytest.raises(ValidationError):
            RecallRequest(query="test", limit=101)


class TestRunSkillRequestValidation:
    """Tests for RunSkillRequest validation."""

    def test_valid_skill_id(self):
        """Test valid skill ID."""
        req = RunSkillRequest(skill_id="my-skill")
        assert req.skill_id == "my-skill"

    def test_empty_skill_id_rejected(self):
        """Test empty skill ID is rejected."""
        with pytest.raises(ValidationError):
            RunSkillRequest(skill_id="")

    def test_long_skill_id_rejected(self):
        """Test overly long skill ID is rejected."""
        with pytest.raises(ValidationError):
            RunSkillRequest(skill_id="x" * 101)
