"""Project detection stub.

This module determines if a user message should trigger autonomous project mode.
For now, it always returns False to allow normal chat flow.
"""

from dataclasses import dataclass


@dataclass
class DetectionResult:
    """Result of project detection."""

    should_project: bool = False
    confidence: float = 0.0
    reason: str = ""
    suggested_name: str = ""


class ProjectDetector:
    """Detects if a message should trigger autonomous project mode."""

    def detect(self, message: str) -> DetectionResult:
        """Analyze message to determine if it should trigger a project.

        Currently returns False for all messages to allow normal chat flow.
        """
        return DetectionResult(
            should_project=False,
            confidence=0.0,
            reason="Project detection disabled",
        )


# Global instance
project_detector = ProjectDetector()
