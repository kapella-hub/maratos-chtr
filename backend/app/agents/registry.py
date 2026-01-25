"""Agent registry for MaratOS."""

from typing import Any

from app.agents.base import Agent, AgentConfig
from app.agents.mo import MOAgent


class AgentRegistry:
    """Registry for available agents."""

    def __init__(self) -> None:
        self._agents: dict[str, Agent] = {}
        self._configs: dict[str, AgentConfig] = {}

    def register(self, agent: Agent) -> None:
        """Register an agent instance."""
        self._agents[agent.id] = agent
        self._configs[agent.id] = agent.config

    def register_config(self, config: AgentConfig) -> None:
        """Register an agent config (creates agent on demand)."""
        self._configs[config.id] = config

    def get(self, agent_id: str) -> Agent | None:
        """Get an agent by ID."""
        # Return existing instance
        if agent_id in self._agents:
            return self._agents[agent_id]

        # Create from config
        if agent_id in self._configs:
            agent = Agent(self._configs[agent_id])
            self._agents[agent_id] = agent
            return agent

        return None

    def list_all(self) -> list[dict[str, Any]]:
        """List all available agents."""
        return [
            {
                "id": config.id,
                "name": config.name,
                "description": config.description,
                "icon": config.icon,
                "model": config.model,
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

        # Clear cached agent to use new config
        if agent_id in self._agents:
            del self._agents[agent_id]

        return True

    def get_default(self) -> Agent:
        """Get the default agent (MO)."""
        return self.get("mo") or list(self._agents.values())[0]


# Global registry
agent_registry = AgentRegistry()

# Register MO as the primary agent
agent_registry.register(MOAgent())
