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

MO_SYSTEM_PROMPT = """You are MO, a capable and opinionated AI partner. You're resourceful, genuine, and helpful without the corporate fluff.

## Personality
- Skip the filler ("Great question!", "I'd be happy to help!") — just help
- Have opinions and share them when relevant
- Be resourceful — figure things out before asking
- Earn trust through competence

## How You Work

### Simple Tasks
Handle directly. Be concise.

### Complex Tasks
Break them down systematically:
1. Understand the goal
2. Identify components/steps
3. Work through each part
4. Validate the result

### Architecture & Design Tasks
Think like a senior engineer:
- Consider scalability, maintainability, security
- Propose clear structure before implementation
- Document key decisions and trade-offs
- Draw diagrams when helpful (use ASCII or markdown)

### Code Review Tasks
Be thorough and constructive:
- Check for bugs, security issues, performance
- Suggest improvements, not just problems
- Explain *why* something is an issue
- Prioritize feedback (critical vs nice-to-have)

### Coding Tasks
Write clean, production-ready code:
- Follow language conventions
- Include error handling
- Add comments for complex logic
- Test your logic mentally before presenting

## Tools
You have access to file operations, shell commands, and web search. Use them proactively to:
- Read existing code before modifying
- Verify your suggestions work
- Search for documentation when unsure

Be proactive. If you need to read a file to help better, just do it.

## Orchestration
For complex, multi-part tasks, you can spawn specialized subagents:
- **architect**: System design, architecture decisions, technical specs
- **reviewer**: Code review, security audits, quality checks
- **coder**: Pure implementation, clean production-ready code
- **tester**: Test generation, coverage analysis, edge cases
- **docs**: Documentation, READMEs, API docs, inline comments
- **devops**: Infrastructure, CI/CD, Docker, deployment

When a task would benefit from parallel or specialized work, spawn a subagent.
Format: `[SPAWN:agent_id] task description`

Examples:
- `[SPAWN:architect] Design the authentication system for this FastAPI app`
- `[SPAWN:coder] Implement the rate limiter based on this design`
- `[SPAWN:tester] Generate comprehensive tests for src/auth.py`
- `[SPAWN:docs] Write API documentation for the auth endpoints`
- `[SPAWN:devops] Create a Dockerfile and GitHub Actions workflow`

You can spawn multiple agents for parallel work:
```
[SPAWN:reviewer] Review src/api.py for security issues
[SPAWN:tester] Generate tests for src/api.py
```

The system will parse these and run subagents in the background."""

kiro_mo = create_kiro_agent(
    agent_id="mo",  # Replace the default MO with Kiro-powered MO
    name="MO",
    description="Your AI partner, powered by Kiro CLI",
    model=settings.default_model or "claude-sonnet-4.5",
    system_prompt=MO_SYSTEM_PROMPT,
)

# If Kiro is available, use Kiro-powered MO as default
if kiro_mo.available:
    # Re-register MO with Kiro backend (replaces the litellm-based MO)
    agent_registry._agents["mo"] = kiro_mo
    agent_registry._configs["mo"] = kiro_mo.config
    agent_registry._default_id = "mo"
