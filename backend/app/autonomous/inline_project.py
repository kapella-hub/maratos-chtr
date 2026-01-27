"""Inline project tracking stub.

This module tracks inline projects within chat sessions.
For now, it returns None to allow normal chat flow.
"""

from enum import Enum
from typing import Optional


class InlineProjectStatus(Enum):
    """Status of an inline project."""

    PLANNING = "planning"
    AWAITING_APPROVAL = "awaiting_approval"
    EXECUTING = "executing"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class InlineProject:
    """Represents an inline project."""

    def __init__(self):
        self.status = InlineProjectStatus.CANCELLED
        self.workspace_path = ""
        self.is_active = False


def get_inline_project(session_id: str) -> Optional[InlineProject]:
    """Get the inline project for a session.

    Currently returns None to disable inline project functionality.
    """
    return None


def create_inline_project(session_id: str, workspace_path: str) -> InlineProject:
    """Create a new inline project."""
    return InlineProject()
