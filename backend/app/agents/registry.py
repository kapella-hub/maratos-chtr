"""Agent registry for MaratOS."""

from typing import Any

from app.agents.base import Agent, AgentConfig
from app.agents.mo import MOAgent
from app.agents.architect import ArchitectAgent
from app.agents.reviewer import ReviewerAgent


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
