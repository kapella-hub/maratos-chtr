"""Agent system for MaratOS."""

from app.agents.base import Agent, AgentConfig
from app.agents.mo import MOAgent
from app.agents.architect import ArchitectAgent
from app.agents.reviewer import ReviewerAgent
from app.agents.registry import agent_registry

__all__ = [
    "Agent",
    "AgentConfig",
    "MOAgent",
    "ArchitectAgent", 
    "ReviewerAgent",
    "agent_registry",
]
