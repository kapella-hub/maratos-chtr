"""Adaptive thinking level selection based on context.

Analyzes messages and context to dynamically select the appropriate
thinking level, rather than using a fixed global setting.
"""

import re
from dataclasses import dataclass, field
from typing import Any

from app.thinking.models import ThinkingLevel
from app.thinking.templates import detect_template, ThinkingTemplate


@dataclass
class ComplexityFactors:
    """Factors used to determine task complexity."""

    message_length: int = 0
    code_blocks: int = 0
    question_marks: int = 0
    technical_terms: int = 0
    file_references: int = 0
    multi_step_indicators: int = 0
    urgency_indicators: int = 0
    error_indicators: int = 0
    architecture_indicators: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "message_length": self.message_length,
            "code_blocks": self.code_blocks,
            "question_marks": self.question_marks,
            "technical_terms": self.technical_terms,
            "file_references": self.file_references,
            "multi_step_indicators": self.multi_step_indicators,
            "urgency_indicators": self.urgency_indicators,
            "error_indicators": self.error_indicators,
            "architecture_indicators": self.architecture_indicators,
        }


@dataclass
class AdaptiveResult:
    """Result of adaptive thinking level determination."""

    original_level: ThinkingLevel
    adaptive_level: ThinkingLevel
    complexity_score: float
    factors: ComplexityFactors
    template: ThinkingTemplate | None = None
    reason: str = ""

    @property
    def was_adjusted(self) -> bool:
        return self.original_level != self.adaptive_level

    def to_dict(self) -> dict[str, Any]:
        return {
            "original_level": self.original_level.value,
            "adaptive_level": self.adaptive_level.value,
            "complexity_score": self.complexity_score,
            "factors": self.factors.to_dict(),
            "template": self.template.id if self.template else None,
            "reason": self.reason,
            "was_adjusted": self.was_adjusted,
        }


class AdaptiveThinkingManager:
    """Manages adaptive thinking level selection.

    Analyzes messages and context to determine the optimal thinking level,
    potentially adjusting up or down from the user's default setting.
    """

    # Technical terms that suggest complexity
    TECHNICAL_TERMS = {
        "algorithm", "architecture", "async", "authentication", "authorization",
        "cache", "concurrency", "database", "dependency", "deployment",
        "encryption", "framework", "interface", "microservice", "migration",
        "optimization", "performance", "refactor", "scalability", "security",
        "transaction", "validation", "vulnerability", "webhook", "api",
    }

    # Patterns for detecting various indicators
    CODE_BLOCK_PATTERN = re.compile(r"```[\s\S]*?```|`[^`]+`")
    FILE_REFERENCE_PATTERN = re.compile(r"[\w/.-]+\.(py|js|ts|tsx|jsx|go|rs|java|rb|php|c|cpp|h|hpp|css|html|json|yaml|yml|md|sql)")
    MULTI_STEP_PATTERN = re.compile(r"\b(first|then|next|after|finally|step\s*\d|1\.|2\.|3\.)\b", re.IGNORECASE)
    URGENCY_PATTERN = re.compile(r"\b(asap|urgent|quickly|fast|hurry|immediately|now)\b", re.IGNORECASE)
    ERROR_PATTERN = re.compile(r"\b(error|bug|crash|fail|broken|issue|problem|exception|traceback)\b", re.IGNORECASE)
    ARCHITECTURE_PATTERN = re.compile(r"\b(design|architect|structure|system|scale|pattern|service|component|module)\b", re.IGNORECASE)
    QUESTION_PATTERN = re.compile(r"\?")

    def __init__(
        self,
        allow_upgrade: bool = True,
        allow_downgrade: bool = True,
        max_upgrade_steps: int = 2,
        max_downgrade_steps: int = 1,
    ):
        """Initialize the adaptive thinking manager.

        Args:
            allow_upgrade: Whether to allow upgrading thinking level
            allow_downgrade: Whether to allow downgrading thinking level
            max_upgrade_steps: Maximum levels to upgrade (e.g., 2 = medium -> high)
            max_downgrade_steps: Maximum levels to downgrade
        """
        self.allow_upgrade = allow_upgrade
        self.allow_downgrade = allow_downgrade
        self.max_upgrade_steps = max_upgrade_steps
        self.max_downgrade_steps = max_downgrade_steps

        # Level ordering for adjustments
        self._level_order = [
            ThinkingLevel.OFF,
            ThinkingLevel.MINIMAL,
            ThinkingLevel.LOW,
            ThinkingLevel.MEDIUM,
            ThinkingLevel.HIGH,
            ThinkingLevel.MAX,
        ]

    def analyze_complexity(self, message: str) -> ComplexityFactors:
        """Analyze a message to determine complexity factors.

        Args:
            message: The user's message

        Returns:
            ComplexityFactors with counts
        """
        factors = ComplexityFactors()

        # Message length (normalized)
        factors.message_length = len(message)

        # Code blocks
        factors.code_blocks = len(self.CODE_BLOCK_PATTERN.findall(message))

        # Question marks
        factors.question_marks = len(self.QUESTION_PATTERN.findall(message))

        # Technical terms
        message_lower = message.lower()
        factors.technical_terms = sum(
            1 for term in self.TECHNICAL_TERMS if term in message_lower
        )

        # File references
        factors.file_references = len(self.FILE_REFERENCE_PATTERN.findall(message))

        # Multi-step indicators
        factors.multi_step_indicators = len(self.MULTI_STEP_PATTERN.findall(message))

        # Urgency indicators
        factors.urgency_indicators = len(self.URGENCY_PATTERN.findall(message))

        # Error indicators
        factors.error_indicators = len(self.ERROR_PATTERN.findall(message))

        # Architecture indicators
        factors.architecture_indicators = len(self.ARCHITECTURE_PATTERN.findall(message))

        return factors

    def calculate_complexity_score(self, factors: ComplexityFactors) -> float:
        """Calculate a complexity score from factors.

        Args:
            factors: ComplexityFactors from analyze_complexity

        Returns:
            Float between 0.0 (simple) and 1.0 (complex)
        """
        # Weighted scoring
        score = 0.0

        # Message length contribution (longer = more complex, up to 0.2)
        length_score = min(factors.message_length / 1000, 1.0) * 0.15
        score += length_score

        # Code blocks (each adds complexity)
        score += min(factors.code_blocks * 0.1, 0.2)

        # Technical terms (strong complexity indicator)
        score += min(factors.technical_terms * 0.05, 0.25)

        # File references (suggests real work)
        score += min(factors.file_references * 0.05, 0.15)

        # Multi-step indicators (multi-part task)
        score += min(factors.multi_step_indicators * 0.05, 0.15)

        # Architecture indicators (high complexity)
        score += min(factors.architecture_indicators * 0.08, 0.2)

        # Error indicators (debugging needs thinking)
        score += min(factors.error_indicators * 0.05, 0.1)

        # Urgency indicators (reduce complexity to be faster)
        score -= min(factors.urgency_indicators * 0.1, 0.2)

        # Clamp to [0, 1]
        return max(0.0, min(1.0, score))

    def _adjust_level(
        self,
        base_level: ThinkingLevel,
        complexity_score: float,
    ) -> tuple[ThinkingLevel, str]:
        """Adjust the thinking level based on complexity score.

        Args:
            base_level: The user's configured thinking level
            complexity_score: Calculated complexity score (0.0-1.0)

        Returns:
            Tuple of (adjusted_level, reason)
        """
        base_index = self._level_order.index(base_level)

        # Determine target based on complexity
        if complexity_score >= 0.7:
            # High complexity - consider upgrading
            target_level = ThinkingLevel.HIGH
            reason = "High complexity detected"
        elif complexity_score >= 0.5:
            # Medium complexity - stay around medium/high
            target_level = ThinkingLevel.MEDIUM
            reason = "Moderate complexity"
        elif complexity_score >= 0.3:
            # Low-medium complexity
            target_level = ThinkingLevel.LOW
            reason = "Lower complexity task"
        else:
            # Simple task
            target_level = ThinkingLevel.MINIMAL
            reason = "Simple task detected"

        target_index = self._level_order.index(target_level)

        # Apply constraints
        if target_index > base_index:
            # Upgrading
            if not self.allow_upgrade:
                return base_level, "Upgrade not allowed"
            max_index = min(base_index + self.max_upgrade_steps, len(self._level_order) - 1)
            final_index = min(target_index, max_index)
        elif target_index < base_index:
            # Downgrading
            if not self.allow_downgrade:
                return base_level, "Downgrade not allowed"
            min_index = max(base_index - self.max_downgrade_steps, 0)
            final_index = max(target_index, min_index)
        else:
            final_index = base_index
            reason = "Level matches complexity"

        return self._level_order[final_index], reason

    def determine_level(
        self,
        message: str,
        base_level: ThinkingLevel,
        context: dict[str, Any] | None = None,
    ) -> AdaptiveResult:
        """Determine the appropriate thinking level for a message.

        Args:
            message: The user's message
            base_level: The user's configured thinking level
            context: Optional additional context (history, errors, etc.)

        Returns:
            AdaptiveResult with the determined level and analysis
        """
        # Detect template first
        template = detect_template(message)

        # Analyze message complexity
        factors = self.analyze_complexity(message)

        # Calculate complexity score
        complexity_score = self.calculate_complexity_score(factors)

        # Consider template minimum level
        if template and template.min_level:
            template_min_index = self._level_order.index(template.min_level)
            base_index = self._level_order.index(base_level)
            if template_min_index > base_index:
                # Template requires higher level
                complexity_score = max(complexity_score, 0.6)

        # Consider context if provided
        if context:
            # Error history suggests need for more careful thinking
            if context.get("recent_errors", 0) > 0:
                complexity_score = min(complexity_score + 0.1, 1.0)

            # User expertise level
            if context.get("user_expertise") == "expert":
                # Experts may want less hand-holding
                complexity_score = max(complexity_score - 0.1, 0.0)
            elif context.get("user_expertise") == "beginner":
                # Beginners benefit from more explanation
                complexity_score = min(complexity_score + 0.1, 1.0)

        # Adjust level based on complexity
        adaptive_level, reason = self._adjust_level(base_level, complexity_score)

        return AdaptiveResult(
            original_level=base_level,
            adaptive_level=adaptive_level,
            complexity_score=complexity_score,
            factors=factors,
            template=template,
            reason=reason,
        )


# Global instance
_adaptive_manager: AdaptiveThinkingManager | None = None


def get_adaptive_manager() -> AdaptiveThinkingManager:
    """Get the global adaptive thinking manager."""
    global _adaptive_manager
    if _adaptive_manager is None:
        _adaptive_manager = AdaptiveThinkingManager()
    return _adaptive_manager


def determine_thinking_level(
    message: str,
    base_level: ThinkingLevel | str,
    context: dict[str, Any] | None = None,
) -> AdaptiveResult:
    """Convenience function to determine thinking level.

    Args:
        message: The user's message
        base_level: The user's configured level (string or enum)
        context: Optional context

    Returns:
        AdaptiveResult
    """
    if isinstance(base_level, str):
        base_level = ThinkingLevel.from_string(base_level)
    return get_adaptive_manager().determine_level(message, base_level, context)
