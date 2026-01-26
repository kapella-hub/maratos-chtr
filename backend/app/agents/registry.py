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
from app.agents.kiro import create_kiro_agent


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
agent_registry.register(CoderAgent())
agent_registry.register(TesterAgent())
agent_registry.register(DocsAgent())
agent_registry.register(DevOpsAgent())

# Kiro CLI agent (Claude via AWS - no API key needed)
# Uses the model from settings.default_model
from app.config import settings

# Import the authoritative MO prompt (single source of truth)
from app.agents.mo import MO_SYSTEM_PROMPT

kiro_mo = create_kiro_agent(
    agent_id="mo",
    name="MO",
    description="Your AI partner, powered by Kiro CLI",
    model=settings.default_model or "claude-sonnet-4.5",
    system_prompt=MO_SYSTEM_PROMPT,
)

# If Kiro is available, replace ALL agents with Kiro-powered versions
if kiro_mo.available:
    # Import system prompts from agent modules
    from app.agents.architect import ARCHITECT_SYSTEM_PROMPT
    from app.agents.reviewer import REVIEWER_SYSTEM_PROMPT
    from app.agents.coder import CODER_SYSTEM_PROMPT
    from app.agents.tester import TESTER_SYSTEM_PROMPT
    from app.agents.docs import DOCS_SYSTEM_PROMPT
    from app.agents.devops import DEVOPS_SYSTEM_PROMPT

    # Create Kiro-powered versions of all agents
    # Format: (id, name, desc, prompt, icon, trust_all_tools)
    # trust_all_tools=True for agents that need to write files (coder, devops)
    kiro_agents = [
        ("mo", "MO", "Your AI partner", MO_SYSTEM_PROMPT, "🤖", False),
        ("architect", "Architect", "System design and architecture", ARCHITECT_SYSTEM_PROMPT, "🏗️", False),
        ("reviewer", "Reviewer", "Code review and security audit", REVIEWER_SYSTEM_PROMPT, "🔍", False),
        ("coder", "Coder", "Clean implementation", CODER_SYSTEM_PROMPT, "💻", True),  # Needs write access
        ("tester", "Tester", "Test generation", TESTER_SYSTEM_PROMPT, "🧪", False),
        ("docs", "Docs", "Documentation", DOCS_SYSTEM_PROMPT, "📝", True),  # May need write access
        ("devops", "DevOps", "Infrastructure and CI/CD", DEVOPS_SYSTEM_PROMPT, "🚀", True),  # Needs write access
    ]

    for agent_id, name, desc, prompt, icon, trust_all in kiro_agents:
        kiro_agent = create_kiro_agent(
            agent_id=agent_id,
            name=name,
            description=desc,
            model=settings.default_model or "claude-sonnet-4.5",
            system_prompt=prompt,
            trust_all_tools=trust_all,
        )
        kiro_agent.config.icon = icon
        agent_registry._agents[agent_id] = kiro_agent
        agent_registry._configs[agent_id] = kiro_agent.config

    agent_registry._default_id = "mo"
