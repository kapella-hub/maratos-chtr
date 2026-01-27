"""Data models for structured thinking.

Provides type-safe models for thinking operations, replacing
the previous XML-based approach with structured JSON.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import uuid4


class ThinkingLevel(str, Enum):
    """Depth of thinking/analysis to perform."""

    OFF = "off"
    MINIMAL = "minimal"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    MAX = "max"

    @property
    def description(self) -> str:
        """Human-readable description of the thinking level."""
        descriptions = {
            "off": "Direct execution without analysis",
            "minimal": "Quick sanity check before execution",
            "low": "Brief problem breakdown",
            "medium": "Structured analysis with approach evaluation",
            "high": "Deep analysis with multiple approaches and risk assessment",
            "max": "Exhaustive analysis with self-critique and validation",
        }
        return descriptions.get(self.value, "Unknown level")

    @property
    def token_budget(self) -> int:
        """Approximate token budget for this thinking level."""
        budgets = {
            "off": 0,
            "minimal": 100,
            "low": 250,
            "medium": 500,
            "high": 1000,
            "max": 2000,
        }
        return budgets.get(self.value, 500)

    @property
    def step_count(self) -> int:
        """Expected number of thinking steps for this level."""
        counts = {
            "off": 0,
            "minimal": 1,
            "low": 2,
            "medium": 3,
            "high": 5,
            "max": 7,
        }
        return counts.get(self.value, 3)

    @classmethod
    def from_string(cls, value: str) -> "ThinkingLevel":
        """Convert string to ThinkingLevel, defaulting to MEDIUM."""
        try:
            return cls(value.lower())
        except ValueError:
            return cls.MEDIUM


class ThinkingStepType(str, Enum):
    """Types of thinking steps."""

    ANALYSIS = "analysis"           # Breaking down the problem
    EVALUATION = "evaluation"       # Weighing options/approaches
    DECISION = "decision"           # Making a choice
    VALIDATION = "validation"       # Checking the decision
    RISK_ASSESSMENT = "risk"        # Identifying potential issues
    IMPLEMENTATION = "implementation"  # Planning execution
    CRITIQUE = "critique"           # Self-review of reasoning


@dataclass
class ThinkingStep:
    """A single step in the thinking process."""

    type: ThinkingStepType
    content: str
    id: str = field(default_factory=lambda: str(uuid4())[:8])
    duration_ms: int = 0
    tokens: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "type": self.type.value,
            "content": self.content,
            "duration_ms": self.duration_ms,
            "tokens": self.tokens,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ThinkingStep":
        """Create from dictionary."""
        return cls(
            id=data.get("id", str(uuid4())[:8]),
            type=ThinkingStepType(data["type"]),
            content=data["content"],
            duration_ms=data.get("duration_ms", 0),
            tokens=data.get("tokens", 0),
            metadata=data.get("metadata", {}),
        )


@dataclass
class ThinkingBlock:
    """A complete thinking block containing multiple steps."""

    level: ThinkingLevel
    steps: list[ThinkingStep] = field(default_factory=list)
    template: str | None = None
    id: str = field(default_factory=lambda: str(uuid4())[:8])
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None
    is_complete: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def total_duration_ms(self) -> int:
        """Total duration of all steps."""
        return sum(step.duration_ms for step in self.steps)

    @property
    def total_tokens(self) -> int:
        """Total tokens used in all steps."""
        return sum(step.tokens for step in self.steps)

    @property
    def step_count(self) -> int:
        """Number of steps in this block."""
        return len(self.steps)

    def add_step(self, step: ThinkingStep) -> None:
        """Add a step to this block."""
        self.steps.append(step)

    def complete(self) -> None:
        """Mark this block as complete."""
        self.completed_at = datetime.utcnow()
        self.is_complete = True

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "level": self.level.value,
            "template": self.template,
            "steps": [step.to_dict() for step in self.steps],
            "total_duration_ms": self.total_duration_ms,
            "total_tokens": self.total_tokens,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "is_complete": self.is_complete,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ThinkingBlock":
        """Create from dictionary."""
        block = cls(
            id=data.get("id", str(uuid4())[:8]),
            level=ThinkingLevel.from_string(data["level"]),
            template=data.get("template"),
            is_complete=data.get("is_complete", False),
            metadata=data.get("metadata", {}),
        )
        block.steps = [ThinkingStep.from_dict(s) for s in data.get("steps", [])]
        if data.get("started_at"):
            block.started_at = datetime.fromisoformat(data["started_at"])
        if data.get("completed_at"):
            block.completed_at = datetime.fromisoformat(data["completed_at"])
        return block

    def to_sse_event(self, event_type: str = "thinking_block") -> str:
        """Convert to Server-Sent Event format."""
        import json
        return f'data: {json.dumps({"type": event_type, "block": self.to_dict()})}\n\n'


@dataclass
class ThinkingSession:
    """A thinking session for a single message/response."""

    message_id: str
    blocks: list[ThinkingBlock] = field(default_factory=list)
    original_level: ThinkingLevel = ThinkingLevel.MEDIUM
    adaptive_level: ThinkingLevel | None = None
    complexity_score: float = 0.5
    id: str = field(default_factory=lambda: str(uuid4())[:8])
    created_at: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def effective_level(self) -> ThinkingLevel:
        """The actual thinking level used (adaptive or original)."""
        return self.adaptive_level or self.original_level

    @property
    def total_duration_ms(self) -> int:
        """Total duration of all blocks."""
        return sum(block.total_duration_ms for block in self.blocks)

    @property
    def total_tokens(self) -> int:
        """Total tokens used in all blocks."""
        return sum(block.total_tokens for block in self.blocks)

    @property
    def total_steps(self) -> int:
        """Total steps across all blocks."""
        return sum(block.step_count for block in self.blocks)

    @property
    def is_complete(self) -> bool:
        """Whether all blocks are complete."""
        return all(block.is_complete for block in self.blocks) if self.blocks else False

    def add_block(self, block: ThinkingBlock) -> None:
        """Add a block to this session."""
        self.blocks.append(block)

    def get_current_block(self) -> ThinkingBlock | None:
        """Get the current (incomplete) block, if any."""
        for block in reversed(self.blocks):
            if not block.is_complete:
                return block
        return None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "message_id": self.message_id,
            "blocks": [block.to_dict() for block in self.blocks],
            "original_level": self.original_level.value,
            "adaptive_level": self.adaptive_level.value if self.adaptive_level else None,
            "effective_level": self.effective_level.value,
            "complexity_score": self.complexity_score,
            "total_duration_ms": self.total_duration_ms,
            "total_tokens": self.total_tokens,
            "total_steps": self.total_steps,
            "is_complete": self.is_complete,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ThinkingSession":
        """Create from dictionary."""
        session = cls(
            id=data.get("id", str(uuid4())[:8]),
            message_id=data["message_id"],
            original_level=ThinkingLevel.from_string(data.get("original_level", "medium")),
            complexity_score=data.get("complexity_score", 0.5),
            metadata=data.get("metadata", {}),
        )
        if data.get("adaptive_level"):
            session.adaptive_level = ThinkingLevel.from_string(data["adaptive_level"])
        session.blocks = [ThinkingBlock.from_dict(b) for b in data.get("blocks", [])]
        if data.get("created_at"):
            session.created_at = datetime.fromisoformat(data["created_at"])
        return session
