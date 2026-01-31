"""Agent registry for MaratOS."""

from typing import Any

from app.agents.base import Agent, AgentConfig
from app.agents.mo import MOAgent
from app.agents.architect import ArchitectAgent
from app.agents.reviewer import ReviewerAgent
from app.agents.coder import CoderAgent
from app.agents.tester import TesterAgent
from app.agents.docs import DocsAgent
from app.agents.devops import DevOpsAgent
# KiroAgent import disabled - base Agent now uses kiro_provider
# from app.agents.kiro import create_kiro_agent


class AgentRegistry:
    """Registry for available agents."""

    def __init__(self) -> None:
        self._agents: dict[str, Agent] = {}
        self._configs: dict[str, AgentConfig] = {}
        self._default_id: str = "mo"

    def register(self, agent: Agent, is_default: bool = False) -> None:
        """Register an agent instance."""
        self._agents[agent.id] = agent
        self._configs[agent.id] = agent.config
        if is_default:
            self._default_id = agent.id

    def register_config(self, config: AgentConfig) -> None:
        """Register an agent config (creates agent on demand)."""
        self._configs[config.id] = config

    def get(self, agent_id: str) -> Agent | None:
        """Get an agent by ID."""
        if agent_id in self._agents:
            return self._agents[agent_id]

        if agent_id in self._configs:
            agent = Agent(self._configs[agent_id])
            self._agents[agent_id] = agent
            return agent

        if agent_id.startswith("dynamic:"):
            # Create dynamic agent
            role_part = agent_id.split(":", 1)[1]
            role_name = role_part.replace("_", " ").title()
            
            config = AgentConfig(
                id=agent_id,
                name=role_name,
                description=f"Dynamic agent specializing in {role_name}",
                icon="⚡",
                model="", # Inherit default
                system_prompt=f"You are a {role_name}. You are a highly skilled specialist in this domain. Focus on providing expert analysis and implementation for tasks related to {role_name}.",
                tools=["filesystem", "web_search", "web_fetch", "shell"], # Standard toolset
            )
            agent = Agent(config)
            self._agents[agent_id] = agent
            return agent

        return None

    def get_default(self) -> Agent:
        """Get the default agent (MO)."""
        return self.get(self._default_id) or list(self._agents.values())[0]

    def list_all(self) -> list[dict[str, Any]]:
        """List all available agents."""
        return [
            {
                "id": config.id,
                "name": config.name,
                "description": config.description,
                "icon": config.icon,
                "model": config.model,
                "is_default": config.id == self._default_id,
            }
            for config in self._configs.values()
        ]

    def get_config(self, agent_id: str) -> AgentConfig | None:
        """Get agent config."""
        return self._configs.get(agent_id)

    def update_config(self, agent_id: str, updates: dict[str, Any]) -> bool:
        """Update agent config."""
        config = self._configs.get(agent_id)
        if not config:
            return False

        for key, value in updates.items():
            if hasattr(config, key):
                setattr(config, key, value)

        if agent_id in self._agents:
            del self._agents[agent_id]

        return True

    def set_default(self, agent_id: str) -> bool:
        """Set the default agent."""
        if agent_id in self._configs:
            self._default_id = agent_id
            return True
        return False


# Global registry
agent_registry = AgentRegistry()

# Register agents
agent_registry.register(MOAgent(), is_default=True)
agent_registry.register(ArchitectAgent())
agent_registry.register(ReviewerAgent())
agent_registry.register(CoderAgent())
agent_registry.register(TesterAgent())
agent_registry.register(DocsAgent())
agent_registry.register(DevOpsAgent())

# NOTE: KiroAgent replacement is DISABLED
# The base Agent class now uses kiro_provider which handles all LLM calls
# through kiro-cli with proper model name translation.
# This avoids the complexity of maintaining two separate kiro integrations.
