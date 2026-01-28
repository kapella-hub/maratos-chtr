"""Project Detection - Determines if a message should trigger project mode.

This module analyzes user messages to detect when they should trigger
the unified orchestration engine in "project mode" rather than normal chat.
"""

import re
from dataclasses import dataclass


@dataclass
class DetectionResult:
    """Result of project detection analysis."""
    should_project: bool = False
    confidence: float = 0.0
    reason: str = ""
    suggested_name: str = ""
    workspace_hint: str | None = None


# Patterns that strongly suggest project mode
PROJECT_PATTERNS = [
    # Explicit project triggers
    (r"\bstart\s+(?:a\s+)?project\b", 0.95, "explicit_project_trigger"),
    (r"\brun\s+(?:in\s+)?project\s+mode\b", 0.98, "explicit_project_mode"),
    (r"\bproject:\s*", 0.95, "project_prefix"),

    # Multi-step implementation requests
    (r"\bimplement\s+(?:a\s+)?(?:full|complete)\s+", 0.85, "full_implementation"),
    (r"\bbuild\s+(?:me\s+)?(?:a\s+|an\s+)?(?:complete|full)\s+", 0.85, "build_complete"),
    (r"\bcreate\s+(?:a\s+)?(?:new\s+)?(?:app|application|system|service)\b", 0.75, "create_app"),

    # Feature requests with tests/docs
    (r"\bwith\s+tests?\b.*\band\b.*\bdocs?\b", 0.80, "tests_and_docs"),
    (r"\bincluding\s+tests?\s+and\s+documentation\b", 0.85, "including_tests_docs"),

    # Multi-file changes
    (r"\bacross\s+(?:multiple|several|all)\s+files\b", 0.75, "multi_file"),
    (r"\brefactor\s+(?:the\s+)?entire\b", 0.80, "refactor_entire"),

    # Architecture requests
    (r"\bdesign\s+and\s+implement\b", 0.85, "design_and_implement"),
    (r"\barchitect\s+(?:a\s+)?solution\b", 0.80, "architect_solution"),
]

# Patterns that suggest NOT using project mode
ANTI_PATTERNS = [
    (r"^\s*(?:what|how|why|when|where|who|can|does|is|are)\s+", 0.7, "question"),
    (r"\bexplain\b", 0.6, "explain_request"),
    (r"\bshow\s+me\b", 0.5, "show_request"),
    (r"\bjust\s+(?:a\s+)?quick\b", 0.7, "quick_task"),
    (r"\bsimple\s+(?:fix|change|update)\b", 0.6, "simple_task"),
    (r"\bone\s+(?:line|file)\b", 0.7, "single_scope"),
]


class ProjectDetector:
    """Detects if a message should trigger orchestrated project mode.

    Uses pattern matching and heuristics to determine confidence level
    that a message warrants full project orchestration vs. simple chat.
    """

    def __init__(self, enabled: bool = True, threshold: float = 0.75):
        """Initialize the detector.

        Args:
            enabled: Whether detection is enabled (False = always return False)
            threshold: Confidence threshold for triggering project mode
        """
        self.enabled = enabled
        self.threshold = threshold

    def detect(self, message: str) -> DetectionResult:
        """Analyze a message to determine if it should trigger project mode.

        Args:
            message: The user's message to analyze

        Returns:
            DetectionResult with detection decision and metadata
        """
        if not self.enabled:
            return DetectionResult(
                should_project=False,
                confidence=0.0,
                reason="Project detection disabled",
            )

        if not message or len(message.strip()) < 10:
            return DetectionResult(
                should_project=False,
                confidence=0.0,
                reason="Message too short",
            )

        message_lower = message.lower()

        # Check anti-patterns first
        anti_score = 0.0
        anti_reason = None
        for pattern, weight, reason in ANTI_PATTERNS:
            if re.search(pattern, message_lower):
                if weight > anti_score:
                    anti_score = weight
                    anti_reason = reason

        # Check project patterns
        project_score = 0.0
        project_reason = None
        for pattern, weight, reason in PROJECT_PATTERNS:
            if re.search(pattern, message_lower):
                if weight > project_score:
                    project_score = weight
                    project_reason = reason

        # Calculate final confidence
        # Anti-patterns reduce confidence
        confidence = max(0, project_score - (anti_score * 0.5))

        # Boost for longer, more detailed requests
        word_count = len(message.split())
        if word_count > 50:
            confidence = min(1.0, confidence + 0.1)
        elif word_count > 100:
            confidence = min(1.0, confidence + 0.15)

        # Extract suggested name from message
        suggested_name = self._extract_project_name(message)

        # Extract workspace hint if mentioned
        workspace_hint = self._extract_workspace(message)

        should_project = confidence >= self.threshold

        if should_project:
            reason = f"Pattern match: {project_reason}" if project_reason else "Heuristic detection"
        elif anti_reason:
            reason = f"Anti-pattern: {anti_reason}"
        else:
            reason = "Confidence below threshold"

        return DetectionResult(
            should_project=should_project,
            confidence=confidence,
            reason=reason,
            suggested_name=suggested_name,
            workspace_hint=workspace_hint,
        )

    def _extract_project_name(self, message: str) -> str:
        """Extract a suggested project name from the message."""
        # Look for explicit project name
        match = re.search(r'project[:\s]+["\']?([^"\']+)["\']?', message, re.IGNORECASE)
        if match:
            return match.group(1).strip()[:50]

        # Look for "build/create/implement X" patterns
        # Order matters - try pattern with suffix first (more precise), then fallback
        patterns = [
            # With app/system/etc suffix (greedy capture before suffix)
            r"(?:build|create|implement)\s+(?:a\s+|an\s+)?([a-z]+(?:-[a-z]+)*)\s+(?:app|application|system|service|feature)",
            # Without suffix (fallback, captures single word)
            r"(?:build|create|implement)\s+(?:a\s+|an\s+)?([a-z]+(?:-[a-z]+)*)(?:\s|$)",
            r"(?:app|application|system|service|feature)\s+(?:for|called|named)\s+[\"']?([^\"']+)[\"']?",
        ]

        for pattern in patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                name = match.group(1).strip()
                # Clean up
                name = re.sub(r"\s+", "-", name)
                name = re.sub(r"[^a-z0-9-]", "", name.lower())
                return name[:50]

        return ""

    def _extract_workspace(self, message: str) -> str | None:
        """Extract workspace path hint from message."""
        patterns = [
            r"(?:in|at|to)\s+[\"']?(/[^\s\"']+)[\"']?",
            r"(?:workspace|directory|folder|path)[:\s]+[\"']?([^\s\"']+)[\"']?",
        ]

        for pattern in patterns:
            match = re.search(pattern, message)
            if match:
                path = match.group(1)
                if path.startswith("/") or path.startswith("~"):
                    return path

        return None


# Global instance - disabled by default for backwards compatibility
# Enable via settings or explicitly
project_detector = ProjectDetector(enabled=False)


def enable_project_detection(enabled: bool = True, threshold: float = 0.75) -> None:
    """Enable or configure project detection globally."""
    global project_detector
    project_detector = ProjectDetector(enabled=enabled, threshold=threshold)
