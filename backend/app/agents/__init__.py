"""Agent system for MaratOS."""

from app.agents.base import Agent, AgentConfig
from app.agents.mo import MOAgent
from app.agents.architect import ArchitectAgent
from app.agents.reviewer import ReviewerAgent
from app.agents.coder import CoderAgent
from app.agents.tester import TesterAgent
from app.agents.docs import DocsAgent
from app.agents.devops import DevOpsAgent
from app.agents.registry import agent_registry

__all__ = [
    "Agent",
    "AgentConfig",
    "MOAgent",
    "ArchitectAgent", 
    "ReviewerAgent",
    "CoderAgent",
    "TesterAgent",
    "DocsAgent",
    "DevOpsAgent",
    "agent_registry",
]
