"""Tests for the task metrics module."""

import pytest
from datetime import datetime, timedelta

from app.subagents.metrics import (
    TaskMetric,
    AgentMetrics,
    TaskSizingRecommendation,
    TaskMetricsManager,
)


class TestTaskMetric:
    """Tests for TaskMetric dataclass."""

    def test_duration_calculation(self):
        """Test that duration is calculated correctly."""
        start = datetime.now()
        end = start + timedelta(seconds=30)
        metric = TaskMetric(
            task_id="test",
            agent_id="coder",
            task_description="Test task",
            started_at=start,
            completed_at=end,
            success=True,
        )
        assert metric.duration_seconds == 30.0

    def test_duration_none_when_incomplete(self):
        """Test that duration is None when not completed."""
        metric = TaskMetric(
            task_id="test",
            agent_id="coder",
            task_description="Test task",
            started_at=datetime.now(),
            success=False,
        )
        assert metric.duration_seconds is None

    def test_goal_completion_rate(self):
        """Test goal completion rate calculation."""
        metric = TaskMetric(
            task_id="test",
            agent_id="coder",
            task_description="Test task",
            started_at=datetime.now(),
            completed_at=datetime.now(),
            success=True,
            goals_total=10,
            goals_completed=7,
        )
        assert metric.goal_completion_rate == 0.7

    def test_goal_completion_rate_no_goals(self):
        """Test goal completion rate when no goals."""
        metric = TaskMetric(
            task_id="test",
            agent_id="coder",
            task_description="Test task",
            started_at=datetime.now(),
            completed_at=datetime.now(),
            success=True,
            goals_total=0,
            goals_completed=0,
        )
        assert metric.goal_completion_rate == 1.0

    def test_to_dict(self):
        """Test serialization to dict."""
        metric = TaskMetric(
            task_id="test",
            agent_id="coder",
            task_description="Test task",
            started_at=datetime.now(),
            completed_at=datetime.now(),
            success=True,
        )
        data = metric.to_dict()
        assert "task_id" in data
        assert "agent_id" in data
        assert "success" in data


class TestAgentMetrics:
    """Tests for AgentMetrics dataclass."""

    def test_success_rate(self):
        """Test success rate calculation."""
        metrics = AgentMetrics(
            agent_id="coder",
            total_tasks=10,
            successful_tasks=8,
            failed_tasks=2,
        )
        assert metrics.success_rate == 0.8

    def test_success_rate_no_tasks(self):
        """Test success rate with no tasks."""
        metrics = AgentMetrics(agent_id="coder")
        assert metrics.success_rate == 0.0

    def test_avg_duration(self):
        """Test average duration calculation."""
        metrics = AgentMetrics(
            agent_id="coder",
            successful_tasks=4,
            total_duration_seconds=120,
        )
        assert metrics.avg_duration_seconds == 30.0

    def test_goal_completion_rate(self):
        """Test goal completion rate."""
        metrics = AgentMetrics(
            agent_id="coder",
            total_goals=100,
            completed_goals=85,
        )
        assert metrics.goal_completion_rate == 0.85


class TestTaskSizingRecommendation:
    """Tests for TaskSizingRecommendation dataclass."""

    def test_to_dict(self):
        """Test serialization."""
        rec = TaskSizingRecommendation(
            agent_id="coder",
            recommended_max_goals=5,
            confidence=0.8,
            reasoning="Based on historical data.",
        )
        data = rec.to_dict()
        assert data["agent_id"] == "coder"
        assert data["recommended_max_goals"] == 5
        assert data["confidence"] == 0.8


class TestTaskMetricsManager:
    """Tests for TaskMetricsManager."""

    def test_record_metric(self):
        """Test recording a metric."""
        manager = TaskMetricsManager()
        metric = manager.record(
            task_id="test1",
            agent_id="coder",
            task_description="Test task",
            started_at=datetime.now(),
            completed_at=datetime.now(),
            success=True,
            goals_total=5,
            goals_completed=5,
        )
        assert metric.task_id == "test1"
        assert metric.success is True

    def test_get_agent_metrics(self):
        """Test aggregating metrics for an agent."""
        manager = TaskMetricsManager()
        now = datetime.now()

        # Record some tasks
        for i in range(5):
            manager.record(
                task_id=f"task{i}",
                agent_id="coder",
                task_description="Test",
                started_at=now,
                completed_at=now + timedelta(seconds=30),
                success=(i < 4),  # 4 successes, 1 failure
                goals_total=3,
                goals_completed=2 if i < 4 else 0,
            )

        metrics = manager.get_agent_metrics("coder")
        assert metrics.total_tasks == 5
        assert metrics.successful_tasks == 4
        assert metrics.failed_tasks == 1
        assert metrics.success_rate == 0.8

    def test_get_sizing_recommendation_insufficient_data(self):
        """Test sizing recommendation with insufficient data."""
        manager = TaskMetricsManager()
        rec = manager.get_sizing_recommendation("coder")
        assert rec.recommended_max_goals == 5
        assert rec.confidence == 0.1
        assert "Insufficient" in rec.reasoning

    def test_get_sizing_recommendation_high_success(self):
        """Test sizing recommendation with high success rate."""
        manager = TaskMetricsManager()
        now = datetime.now()

        # Record 10 successful tasks
        for i in range(10):
            manager.record(
                task_id=f"task{i}",
                agent_id="coder",
                task_description="Test",
                started_at=now,
                completed_at=now + timedelta(seconds=30),
                success=True,
                goals_total=5,
                goals_completed=5,
            )

        rec = manager.get_sizing_recommendation("coder")
        assert rec.recommended_max_goals >= 5
        assert rec.confidence > 0.1
        assert "success rate" in rec.reasoning.lower()

    def test_max_history_limit(self):
        """Test that metrics are trimmed to max history."""
        manager = TaskMetricsManager(max_history=10)
        now = datetime.now()

        # Record more than max_history tasks
        for i in range(15):
            manager.record(
                task_id=f"task{i}",
                agent_id="coder",
                task_description="Test",
                started_at=now,
                completed_at=now,
                success=True,
            )

        # Should only keep last 10
        assert len(manager._metrics) == 10

    def test_get_recent_metrics(self):
        """Test getting recent metrics."""
        manager = TaskMetricsManager()
        now = datetime.now()

        for i in range(5):
            manager.record(
                task_id=f"task{i}",
                agent_id="coder",
                task_description="Test",
                started_at=now,
                completed_at=now,
                success=True,
            )

        recent = manager.get_recent_metrics(limit=3)
        assert len(recent) == 3

    def test_get_failure_patterns(self):
        """Test analyzing failure patterns."""
        manager = TaskMetricsManager()
        now = datetime.now()

        # Record some failures with different errors
        manager.record(
            task_id="t1",
            agent_id="coder",
            task_description="Test",
            started_at=now,
            completed_at=now,
            success=False,
            error="Connection timeout",
        )
        manager.record(
            task_id="t2",
            agent_id="coder",
            task_description="Test",
            started_at=now,
            completed_at=now,
            success=False,
            error="Rate limit exceeded",
        )
        manager.record(
            task_id="t3",
            agent_id="coder",
            task_description="Test",
            started_at=now,
            completed_at=now,
            success=False,
            error="File not found",
        )

        patterns = manager.get_failure_patterns()
        assert patterns.get("timeout") == 1
        assert patterns.get("rate_limit") == 1
        assert patterns.get("not_found") == 1

    def test_clear(self):
        """Test clearing all metrics."""
        manager = TaskMetricsManager()
        manager.record(
            task_id="t1",
            agent_id="coder",
            task_description="Test",
            started_at=datetime.now(),
            completed_at=datetime.now(),
            success=True,
        )

        manager.clear()
        assert len(manager._metrics) == 0
