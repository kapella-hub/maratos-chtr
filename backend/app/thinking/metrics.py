"""Thinking metrics tracking and analysis.

Tracks thinking performance metrics to enable:
- Understanding which thinking levels produce better outcomes
- Optimizing token usage
- Identifying patterns in thinking effectiveness
"""

import json
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from app.thinking.models import ThinkingLevel, ThinkingSession


@dataclass
class ThinkingMetricEntry:
    """A single metric entry for a thinking session."""

    session_id: str
    message_id: str
    level: ThinkingLevel
    adaptive_level: ThinkingLevel | None
    template: str | None
    duration_ms: int
    tokens_used: int
    step_count: int
    complexity_score: float
    outcome: str | None = None  # "success", "error", "retry", etc.
    user_feedback: int | None = None  # -1, 0, 1 for negative/neutral/positive
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "message_id": self.message_id,
            "level": self.level.value,
            "adaptive_level": self.adaptive_level.value if self.adaptive_level else None,
            "template": self.template,
            "duration_ms": self.duration_ms,
            "tokens_used": self.tokens_used,
            "step_count": self.step_count,
            "complexity_score": self.complexity_score,
            "outcome": self.outcome,
            "user_feedback": self.user_feedback,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ThinkingMetricEntry":
        return cls(
            session_id=data["session_id"],
            message_id=data["message_id"],
            level=ThinkingLevel.from_string(data["level"]),
            adaptive_level=ThinkingLevel.from_string(data["adaptive_level"]) if data.get("adaptive_level") else None,
            template=data.get("template"),
            duration_ms=data.get("duration_ms", 0),
            tokens_used=data.get("tokens_used", 0),
            step_count=data.get("step_count", 0),
            complexity_score=data.get("complexity_score", 0.5),
            outcome=data.get("outcome"),
            user_feedback=data.get("user_feedback"),
            timestamp=datetime.fromisoformat(data["timestamp"]) if data.get("timestamp") else datetime.utcnow(),
        )

    @classmethod
    def from_session(cls, session: ThinkingSession) -> "ThinkingMetricEntry":
        """Create a metric entry from a ThinkingSession."""
        return cls(
            session_id=session.id,
            message_id=session.message_id,
            level=session.original_level,
            adaptive_level=session.adaptive_level,
            template=session.blocks[0].template if session.blocks else None,
            duration_ms=session.total_duration_ms,
            tokens_used=session.total_tokens,
            step_count=session.total_steps,
            complexity_score=session.complexity_score,
        )


@dataclass
class AggregateMetrics:
    """Aggregated metrics for a time period or level."""

    total_sessions: int = 0
    total_duration_ms: int = 0
    total_tokens: int = 0
    total_steps: int = 0
    success_count: int = 0
    error_count: int = 0
    retry_count: int = 0
    positive_feedback: int = 0
    negative_feedback: int = 0
    neutral_feedback: int = 0

    @property
    def avg_duration_ms(self) -> float:
        return self.total_duration_ms / max(self.total_sessions, 1)

    @property
    def avg_tokens(self) -> float:
        return self.total_tokens / max(self.total_sessions, 1)

    @property
    def avg_steps(self) -> float:
        return self.total_steps / max(self.total_sessions, 1)

    @property
    def success_rate(self) -> float:
        total = self.success_count + self.error_count + self.retry_count
        return self.success_count / max(total, 1)

    @property
    def feedback_score(self) -> float:
        """Calculate average feedback score (-1 to 1)."""
        total = self.positive_feedback + self.negative_feedback + self.neutral_feedback
        if total == 0:
            return 0.0
        return (self.positive_feedback - self.negative_feedback) / total

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_sessions": self.total_sessions,
            "total_duration_ms": self.total_duration_ms,
            "total_tokens": self.total_tokens,
            "total_steps": self.total_steps,
            "avg_duration_ms": self.avg_duration_ms,
            "avg_tokens": self.avg_tokens,
            "avg_steps": self.avg_steps,
            "success_count": self.success_count,
            "error_count": self.error_count,
            "retry_count": self.retry_count,
            "success_rate": self.success_rate,
            "positive_feedback": self.positive_feedback,
            "negative_feedback": self.negative_feedback,
            "neutral_feedback": self.neutral_feedback,
            "feedback_score": self.feedback_score,
        }


class ThinkingMetrics:
    """Tracks and analyzes thinking metrics.

    Stores metrics in memory with optional persistence to disk.
    Provides aggregation and analysis methods.
    """

    def __init__(
        self,
        persist_path: Path | str | None = None,
        max_entries: int = 10000,
    ):
        """Initialize the metrics tracker.

        Args:
            persist_path: Optional path to persist metrics
            max_entries: Maximum entries to keep in memory
        """
        self._entries: list[ThinkingMetricEntry] = []
        self._max_entries = max_entries
        self._persist_path = Path(persist_path) if persist_path else None

        # Load existing metrics if persistence is enabled
        if self._persist_path and self._persist_path.exists():
            self._load()

    def record(self, session: ThinkingSession, outcome: str | None = None) -> ThinkingMetricEntry:
        """Record metrics from a thinking session.

        Args:
            session: The completed thinking session
            outcome: Optional outcome ("success", "error", "retry")

        Returns:
            The created metric entry
        """
        entry = ThinkingMetricEntry.from_session(session)
        entry.outcome = outcome
        self._add_entry(entry)
        return entry

    def record_entry(self, entry: ThinkingMetricEntry) -> None:
        """Record a pre-created metric entry."""
        self._add_entry(entry)

    def record_feedback(
        self,
        message_id: str,
        feedback: int,
    ) -> bool:
        """Record user feedback for a message.

        Args:
            message_id: The message ID
            feedback: -1 (negative), 0 (neutral), or 1 (positive)

        Returns:
            True if entry was found and updated
        """
        for entry in reversed(self._entries):
            if entry.message_id == message_id:
                entry.user_feedback = feedback
                self._save()
                return True
        return False

    def record_outcome(
        self,
        message_id: str,
        outcome: str,
    ) -> bool:
        """Record outcome for a message.

        Args:
            message_id: The message ID
            outcome: "success", "error", "retry", etc.

        Returns:
            True if entry was found and updated
        """
        for entry in reversed(self._entries):
            if entry.message_id == message_id:
                entry.outcome = outcome
                self._save()
                return True
        return False

    def _add_entry(self, entry: ThinkingMetricEntry) -> None:
        """Add an entry, maintaining max size."""
        self._entries.append(entry)

        # Trim if over max
        if len(self._entries) > self._max_entries:
            self._entries = self._entries[-self._max_entries:]

        self._save()

    def get_entries(
        self,
        since: datetime | None = None,
        level: ThinkingLevel | None = None,
        template: str | None = None,
        limit: int | None = None,
    ) -> list[ThinkingMetricEntry]:
        """Get filtered metric entries.

        Args:
            since: Only entries after this time
            level: Filter by thinking level
            template: Filter by template
            limit: Maximum entries to return

        Returns:
            List of matching entries
        """
        entries = self._entries

        if since:
            entries = [e for e in entries if e.timestamp >= since]
        if level:
            entries = [e for e in entries if e.level == level or e.adaptive_level == level]
        if template:
            entries = [e for e in entries if e.template == template]

        if limit:
            entries = entries[-limit:]

        return entries

    def aggregate(
        self,
        since: datetime | None = None,
        level: ThinkingLevel | None = None,
        template: str | None = None,
    ) -> AggregateMetrics:
        """Get aggregated metrics.

        Args:
            since: Only include entries after this time
            level: Filter by thinking level
            template: Filter by template

        Returns:
            AggregateMetrics for the filtered entries
        """
        entries = self.get_entries(since=since, level=level, template=template)
        agg = AggregateMetrics()

        for entry in entries:
            agg.total_sessions += 1
            agg.total_duration_ms += entry.duration_ms
            agg.total_tokens += entry.tokens_used
            agg.total_steps += entry.step_count

            if entry.outcome == "success":
                agg.success_count += 1
            elif entry.outcome == "error":
                agg.error_count += 1
            elif entry.outcome == "retry":
                agg.retry_count += 1

            if entry.user_feedback == 1:
                agg.positive_feedback += 1
            elif entry.user_feedback == -1:
                agg.negative_feedback += 1
            elif entry.user_feedback == 0:
                agg.neutral_feedback += 1

        return agg

    def aggregate_by_level(
        self,
        since: datetime | None = None,
    ) -> dict[str, AggregateMetrics]:
        """Get metrics aggregated by thinking level.

        Args:
            since: Only include entries after this time

        Returns:
            Dict mapping level name to AggregateMetrics
        """
        result = {}
        for level in ThinkingLevel:
            metrics = self.aggregate(since=since, level=level)
            if metrics.total_sessions > 0:
                result[level.value] = metrics
        return result

    def aggregate_by_template(
        self,
        since: datetime | None = None,
    ) -> dict[str, AggregateMetrics]:
        """Get metrics aggregated by template.

        Args:
            since: Only include entries after this time

        Returns:
            Dict mapping template name to AggregateMetrics
        """
        # Get unique templates
        entries = self.get_entries(since=since)
        templates = set(e.template for e in entries if e.template)

        result = {}
        for template in templates:
            metrics = self.aggregate(since=since, template=template)
            if metrics.total_sessions > 0:
                result[template] = metrics

        return result

    def get_level_effectiveness(
        self,
        since: datetime | None = None,
    ) -> dict[str, dict[str, float]]:
        """Analyze effectiveness of different thinking levels.

        Returns dict with level -> {success_rate, avg_duration, avg_tokens, feedback_score}
        """
        by_level = self.aggregate_by_level(since)

        result = {}
        for level, metrics in by_level.items():
            result[level] = {
                "success_rate": metrics.success_rate,
                "avg_duration_ms": metrics.avg_duration_ms,
                "avg_tokens": metrics.avg_tokens,
                "feedback_score": metrics.feedback_score,
                "total_sessions": metrics.total_sessions,
            }

        return result

    def suggest_level(
        self,
        complexity_score: float,
        template: str | None = None,
    ) -> ThinkingLevel:
        """Suggest a thinking level based on historical performance.

        Uses past metrics to recommend a level that balances
        success rate with efficiency.

        Args:
            complexity_score: Task complexity (0.0-1.0)
            template: Optional template for context

        Returns:
            Recommended ThinkingLevel
        """
        # Get recent metrics by level
        since = datetime.utcnow() - timedelta(days=7)
        effectiveness = self.get_level_effectiveness(since)

        if not effectiveness:
            # No data - use complexity-based default
            if complexity_score >= 0.7:
                return ThinkingLevel.HIGH
            elif complexity_score >= 0.4:
                return ThinkingLevel.MEDIUM
            else:
                return ThinkingLevel.LOW

        # Score each level
        best_level = ThinkingLevel.MEDIUM
        best_score = 0.0

        for level_str, metrics in effectiveness.items():
            level = ThinkingLevel.from_string(level_str)

            # Skip if too few samples
            if metrics["total_sessions"] < 5:
                continue

            # Calculate composite score
            # Higher success rate and feedback = better
            # Lower tokens = better (efficiency)
            success_score = metrics["success_rate"] * 0.4
            feedback_score = (metrics["feedback_score"] + 1) / 2 * 0.3  # Normalize to 0-1
            efficiency_score = (1 - min(metrics["avg_tokens"] / 1000, 1)) * 0.3

            composite = success_score + feedback_score + efficiency_score

            # Adjust for complexity match
            level_complexity = {
                ThinkingLevel.OFF: 0.0,
                ThinkingLevel.MINIMAL: 0.2,
                ThinkingLevel.LOW: 0.4,
                ThinkingLevel.MEDIUM: 0.6,
                ThinkingLevel.HIGH: 0.8,
                ThinkingLevel.MAX: 1.0,
            }
            complexity_match = 1 - abs(complexity_score - level_complexity.get(level, 0.5))
            composite *= (0.7 + complexity_match * 0.3)  # Up to 30% bonus for match

            if composite > best_score:
                best_score = composite
                best_level = level

        return best_level

    def get_summary(self) -> dict[str, Any]:
        """Get a summary of all metrics."""
        total = self.aggregate()
        by_level = self.aggregate_by_level()
        by_template = self.aggregate_by_template()

        return {
            "total": total.to_dict(),
            "by_level": {k: v.to_dict() for k, v in by_level.items()},
            "by_template": {k: v.to_dict() for k, v in by_template.items()},
            "entry_count": len(self._entries),
        }

    def _save(self) -> None:
        """Save metrics to disk if persistence is enabled."""
        if not self._persist_path:
            return

        try:
            self._persist_path.parent.mkdir(parents=True, exist_ok=True)
            data = [e.to_dict() for e in self._entries]
            self._persist_path.write_text(json.dumps(data, indent=2))
        except Exception as e:
            # Don't fail on persistence errors
            pass

    def _load(self) -> None:
        """Load metrics from disk."""
        if not self._persist_path or not self._persist_path.exists():
            return

        try:
            data = json.loads(self._persist_path.read_text())
            self._entries = [ThinkingMetricEntry.from_dict(d) for d in data]
        except Exception:
            self._entries = []


# Global instance
_metrics: ThinkingMetrics | None = None


def get_metrics(persist_path: Path | str | None = None) -> ThinkingMetrics:
    """Get the global thinking metrics instance."""
    global _metrics
    if _metrics is None:
        # Default persistence path
        if persist_path is None:
            persist_path = Path.home() / ".maratos" / "thinking_metrics.json"
        _metrics = ThinkingMetrics(persist_path=persist_path)
    return _metrics
