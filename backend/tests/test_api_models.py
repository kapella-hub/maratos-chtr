"""Tests for API response models."""

from datetime import datetime

import pytest

from app.api.models import (
    StatusResponse,
    ErrorDetail,
    HealthResponse,
    TaskResponse,
    MemoryResponse,
    SkillResponse,
    AgentResponse,
    ConfigResponse,
)


class TestStatusResponse:
    """Tests for StatusResponse model."""

    def test_basic_status(self):
        """Test basic status response."""
        resp = StatusResponse(status="ok")
        assert resp.status == "ok"

    def test_serialization(self):
        """Test model can be serialized."""
        resp = StatusResponse(status="deleted")
        data = resp.model_dump()
        assert data == {"status": "deleted"}


class TestHealthResponse:
    """Tests for HealthResponse model."""

    def test_all_fields(self):
        """Test health response with all fields."""
        resp = HealthResponse(
            status="ok",
            version="0.1.0",
            agent="MO",
            channels=2,
            skills=10,
            memories=100,
            running_tasks=3,
        )
        assert resp.status == "ok"
        assert resp.version == "0.1.0"
        assert resp.agent == "MO"
        assert resp.channels == 2
        assert resp.skills == 10
        assert resp.memories == 100
        assert resp.running_tasks == 3

    def test_serialization(self):
        """Test model serialization includes all fields."""
        resp = HealthResponse(
            status="ok",
            version="0.1.0",
            agent="MO",
            channels=0,
            skills=0,
            memories=0,
            running_tasks=0,
        )
        data = resp.model_dump()
        assert len(data) == 7


class TestTaskResponse:
    """Tests for TaskResponse model."""

    def test_required_fields(self):
        """Test task response with required fields."""
        now = datetime.now()
        resp = TaskResponse(
            id="task-123",
            name="Test Task",
            description="A test task",
            agent_id="mo",
            status="running",
            progress=0.5,
            created_at=now,
        )
        assert resp.id == "task-123"
        assert resp.status == "running"
        assert resp.progress == 0.5

    def test_optional_fields(self):
        """Test task response optional fields default to None."""
        now = datetime.now()
        resp = TaskResponse(
            id="task-123",
            name="Test Task",
            description="A test task",
            agent_id="mo",
            status="pending",
            progress=0.0,
            created_at=now,
        )
        assert resp.result is None
        assert resp.error is None
        assert resp.completed_at is None


class TestMemoryResponse:
    """Tests for MemoryResponse model."""

    def test_all_fields(self):
        """Test memory response with all fields."""
        now = datetime.now()
        resp = MemoryResponse(
            id="mem-123",
            content="Important fact",
            memory_type="fact",
            importance=0.8,
            tags=["important", "fact"],
            created_at=now,
        )
        assert resp.id == "mem-123"
        assert resp.importance == 0.8
        assert len(resp.tags) == 2


class TestAgentResponse:
    """Tests for AgentResponse model."""

    def test_all_fields(self):
        """Test agent response with all fields."""
        resp = AgentResponse(
            id="mo",
            name="MO",
            description="Primary orchestrator",
            icon="🤖",
            model="claude-sonnet-4",
            temperature=0.7,
        )
        assert resp.id == "mo"
        assert resp.temperature == 0.7


class TestConfigResponse:
    """Tests for ConfigResponse model."""

    def test_all_fields(self):
        """Test config response with all fields."""
        resp = ConfigResponse(
            app_name="MaratOS",
            debug=False,
            default_model="claude-sonnet-4",
            max_context_tokens=100000,
            max_response_tokens=8192,
        )
        assert resp.app_name == "MaratOS"
        assert resp.debug is False
