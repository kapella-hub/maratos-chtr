"""Subagent system for MaratOS - spawn background tasks."""

from app.subagents.manager import SubagentManager, SubagentTask
from app.subagents.runner import SubagentRunner

__all__ = ["SubagentManager", "SubagentTask", "SubagentRunner"]
