"""Inline orchestrator stub.

This module handles inline project orchestration within chat sessions.
For now, it provides minimal stubs to allow normal chat flow.
"""

from typing import Any, AsyncIterator
from dataclasses import dataclass


@dataclass
class InlineEvent:
    """Event from inline orchestrator."""

    type: str
    data: dict

    def to_sse(self) -> str:
        """Convert to SSE format."""
        import json
        return f'data: {json.dumps({"type": self.type, **self.data})}\n\n'


class InlineOrchestrator:
    """Orchestrates inline projects within chat sessions."""

    def __init__(self, session_id: str, workspace_path: str = ""):
        self.session_id = session_id
        self.workspace_path = workspace_path
        self.project = None

    async def approve_plan(self) -> AsyncIterator[InlineEvent]:
        """Approve and start plan execution."""
        yield InlineEvent(type="info", data={"message": "Plan approval not implemented"})

    async def cancel_project(self) -> AsyncIterator[InlineEvent]:
        """Cancel the project."""
        yield InlineEvent(type="cancelled", data={"message": "Project cancelled"})

    async def adjust_plan(self, adjustments: dict) -> AsyncIterator[InlineEvent]:
        """Adjust the plan based on feedback."""
        yield InlineEvent(type="info", data={"message": "Plan adjustment not implemented"})

    async def _handle_interrupt(self, message: str) -> AsyncIterator[InlineEvent]:
        """Handle an interrupt during execution."""
        yield InlineEvent(type="info", data={"message": "Interrupt handling not implemented"})


async def handle_project_action(
    session_id: str,
    action: str,
    data: dict | None = None,
) -> AsyncIterator[InlineEvent]:
    """Handle a project action request."""
    yield InlineEvent(type="error", data={"message": f"Project action '{action}' not implemented"})
