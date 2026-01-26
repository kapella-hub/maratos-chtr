"""Task metrics for tracking performance and adaptive sizing."""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class TaskMetric:
    """Metrics for a single task execution."""

    task_id: str
    agent_id: str
    task_description: str
    started_at: datetime
    completed_at: datetime | None = None
    success: bool = False
    goals_total: int = 0
    goals_completed: int = 0
    error: str | None = None

    @property
    def duration_seconds(self) -> float | None:
        """Get task duration in seconds."""
        if self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    @property
    def goal_completion_rate(self) -> float:
        """Get goal completion rate (0-1)."""
        if self.goals_total == 0:
            return 1.0 if self.success else 0.0
        return self.goals_completed / self.goals_total

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "agent_id": self.agent_id,
            "task_description": self.task_description[:100],
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "success": self.success,
            "duration_seconds": self.duration_seconds,
            "goals_total": self.goals_total,
            "goals_completed": self.goals_completed,
            "goal_completion_rate": self.goal_completion_rate,
            "error": self.error,
        }


@dataclass
class AgentMetrics:
    """Aggregated metrics for an agent."""

    agent_id: str
    total_tasks: int = 0
    successful_tasks: int = 0
    failed_tasks: int = 0
    total_duration_seconds: float = 0.0
    total_goals: int = 0
    completed_goals: int = 0

    @property
    def success_rate(self) -> float:
        """Success rate (0-1)."""
        if self.total_tasks == 0:
            return 0.0
        return self.successful_tasks / self.total_tasks

    @property
    def avg_duration_seconds(self) -> float:
        """Average task duration."""
        if self.successful_tasks == 0:
            return 0.0
        return self.total_duration_seconds / self.successful_tasks

    @property
    def goal_completion_rate(self) -> float:
        """Overall goal completion rate."""
        if self.total_goals == 0:
            return 0.0
        return self.completed_goals / self.total_goals

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "total_tasks": self.total_tasks,
            "successful_tasks": self.successful_tasks,
            "failed_tasks": self.failed_tasks,
            "success_rate": round(self.success_rate, 2),
            "avg_duration_seconds": round(self.avg_duration_seconds, 1),
            "total_goals": self.total_goals,
            "completed_goals": self.completed_goals,
            "goal_completion_rate": round(self.goal_completion_rate, 2),
        }


@dataclass
class TaskSizingRecommendation:
    """Recommendation for task sizing based on metrics."""

    agent_id: str
    recommended_max_goals: int
    confidence: float  # 0-1 based on sample size
    reasoning: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "recommended_max_goals": self.recommended_max_goals,
            "confidence": round(self.confidence, 2),
            "reasoning": self.reasoning,
        }


class TaskMetricsManager:
    """Manages task metrics collection and analysis."""

    def __init__(self, max_history: int = 500) -> None:
        self._metrics: list[TaskMetric] = []
        self._max_history = max_history

    def record(
        self,
        task_id: str,
        agent_id: str,
        task_description: str,
        started_at: datetime,
        completed_at: datetime,
        success: bool,
        goals_total: int = 0,
        goals_completed: int = 0,
        error: str | None = None,
    ) -> TaskMetric:
        """Record metrics for a completed task."""
        metric = TaskMetric(
            task_id=task_id,
            agent_id=agent_id,
            task_description=task_description,
            started_at=started_at,
            completed_at=completed_at,
            success=success,
            goals_total=goals_total,
            goals_completed=goals_completed,
            error=error,
        )

        self._metrics.append(metric)

        # Trim old metrics
        if len(self._metrics) > self._max_history:
            self._metrics = self._metrics[-self._max_history :]

        logger.info(
            f"Recorded metrics for task {task_id}: "
            f"success={success}, duration={metric.duration_seconds:.1f}s, "
            f"goals={goals_completed}/{goals_total}"
        )

        return metric

    def get_agent_metrics(
        self,
        agent_id: str,
        since: datetime | None = None,
    ) -> AgentMetrics:
        """Get aggregated metrics for an agent."""
        if since is None:
            since = datetime.now() - timedelta(days=7)

        metrics = AgentMetrics(agent_id=agent_id)

        for m in self._metrics:
            if m.agent_id != agent_id:
                continue
            if m.started_at < since:
                continue

            metrics.total_tasks += 1
            metrics.total_goals += m.goals_total
            metrics.completed_goals += m.goals_completed

            if m.success:
                metrics.successful_tasks += 1
                if m.duration_seconds:
                    metrics.total_duration_seconds += m.duration_seconds
            else:
                metrics.failed_tasks += 1

        return metrics

    def get_all_agent_metrics(
        self,
        since: datetime | None = None,
    ) -> dict[str, AgentMetrics]:
        """Get aggregated metrics for all agents."""
        agent_ids = set(m.agent_id for m in self._metrics)
        return {
            agent_id: self.get_agent_metrics(agent_id, since)
            for agent_id in agent_ids
        }

    def get_sizing_recommendation(self, agent_id: str) -> TaskSizingRecommendation:
        """Get task sizing recommendation based on historical performance."""
        metrics = self.get_agent_metrics(agent_id)

        # Base recommendation
        base_goals = 5
        confidence = 0.0
        reasoning_parts = []

        if metrics.total_tasks < 3:
            # Not enough data
            return TaskSizingRecommendation(
                agent_id=agent_id,
                recommended_max_goals=base_goals,
                confidence=0.1,
                reasoning="Insufficient data (less than 3 tasks). Using default of 5 goals.",
            )

        # Calculate confidence based on sample size
        confidence = min(1.0, metrics.total_tasks / 20)
        reasoning_parts.append(f"Based on {metrics.total_tasks} tasks")

        # Adjust based on success rate
        if metrics.success_rate >= 0.9:
            base_goals = 7
            reasoning_parts.append(f"High success rate ({metrics.success_rate:.0%}) suggests more goals possible")
        elif metrics.success_rate >= 0.7:
            base_goals = 5
            reasoning_parts.append(f"Good success rate ({metrics.success_rate:.0%}) suggests standard sizing")
        elif metrics.success_rate >= 0.5:
            base_goals = 4
            reasoning_parts.append(f"Moderate success rate ({metrics.success_rate:.0%}) suggests smaller tasks")
        else:
            base_goals = 3
            reasoning_parts.append(f"Low success rate ({metrics.success_rate:.0%}) suggests minimal goals")

        # Adjust based on goal completion rate
        if metrics.goal_completion_rate < 0.5:
            base_goals = max(3, base_goals - 2)
            reasoning_parts.append(f"Low goal completion ({metrics.goal_completion_rate:.0%}) reduces recommendation")
        elif metrics.goal_completion_rate > 0.9:
            base_goals = min(10, base_goals + 1)
            reasoning_parts.append(f"High goal completion ({metrics.goal_completion_rate:.0%}) increases recommendation")

        # Consider duration
        if metrics.avg_duration_seconds > 300:  # > 5 minutes
            base_goals = max(3, base_goals - 1)
            reasoning_parts.append(f"Long avg duration ({metrics.avg_duration_seconds:.0f}s) suggests smaller scope")

        return TaskSizingRecommendation(
            agent_id=agent_id,
            recommended_max_goals=base_goals,
            confidence=confidence,
            reasoning=". ".join(reasoning_parts) + ".",
        )

    def get_recent_metrics(self, limit: int = 20) -> list[TaskMetric]:
        """Get recent task metrics."""
        return self._metrics[-limit:]

    def get_failure_patterns(self, agent_id: str | None = None) -> dict[str, int]:
        """Analyze common failure patterns."""
        patterns: dict[str, int] = {}

        for m in self._metrics:
            if agent_id and m.agent_id != agent_id:
                continue
            if not m.success and m.error:
                # Normalize error message
                error_key = m.error[:100].lower()
                if "timeout" in error_key:
                    patterns["timeout"] = patterns.get("timeout", 0) + 1
                elif "memory" in error_key:
                    patterns["memory"] = patterns.get("memory", 0) + 1
                elif "rate limit" in error_key:
                    patterns["rate_limit"] = patterns.get("rate_limit", 0) + 1
                elif "not found" in error_key:
                    patterns["not_found"] = patterns.get("not_found", 0) + 1
                else:
                    patterns["other"] = patterns.get("other", 0) + 1

        return patterns

    def clear(self) -> None:
        """Clear all metrics."""
        self._metrics.clear()
        logger.info("Cleared all task metrics")


# Global metrics manager
task_metrics = TaskMetricsManager()
