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

## Think Step-by-Step (MANDATORY)
Before EVERY response, you MUST:

<thinking>
1. What exactly is the user asking?
2. What context do I need? (Read files first)
3. Which agents should handle this?
4. What's my plan?
</thinking>

Then respond. The <thinking> block shows your reasoning process.

For complex tasks, ALWAYS delegate to specialists.

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

## Orchestration — USE THIS!
You have a team of specialized agents. **ALWAYS delegate** to them for their specialties:

| Task Type | Agent | Spawn Command |
|-----------|-------|---------------|
| Code review, security audit | reviewer | `[SPAWN:reviewer] Review X for security issues` |
| Architecture, system design | architect | `[SPAWN:architect] Design the auth system` |
| Implementation | coder | `[SPAWN:coder] Implement the rate limiter` |
| Test generation | tester | `[SPAWN:tester] Generate tests for X` |
| Documentation | docs | `[SPAWN:docs] Document the API endpoints` |
| DevOps, CI/CD, Docker | devops | `[SPAWN:devops] Create deployment config` |

**Rules:**
1. For code analysis/review → ALWAYS spawn `reviewer`
2. For architecture questions → ALWAYS spawn `architect`  
3. For "write tests" → ALWAYS spawn `tester`
4. For documentation → ALWAYS spawn `docs`
5. You can spawn multiple agents in one response

**Format:** Put spawn commands on their own line:
```
I'll have the team analyze this codebase.

[SPAWN:reviewer] Review /path/to/code for security vulnerabilities and code quality issues

[SPAWN:architect] Analyze the architecture of /path/to/code and suggest improvements
```

The agents will work in parallel and report back. You coordinate and summarize."""

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
    kiro_agents = [
        ("mo", "MO", "Your AI partner", MO_SYSTEM_PROMPT, "🤖"),
        ("architect", "Architect", "System design and architecture", ARCHITECT_SYSTEM_PROMPT, "🏗️"),
        ("reviewer", "Reviewer", "Code review and security audit", REVIEWER_SYSTEM_PROMPT, "🔍"),
        ("coder", "Coder", "Clean implementation", CODER_SYSTEM_PROMPT, "💻"),
        ("tester", "Tester", "Test generation", TESTER_SYSTEM_PROMPT, "🧪"),
        ("docs", "Docs", "Documentation", DOCS_SYSTEM_PROMPT, "📝"),
        ("devops", "DevOps", "Infrastructure and CI/CD", DEVOPS_SYSTEM_PROMPT, "🚀"),
    ]
    
    for agent_id, name, desc, prompt, icon in kiro_agents:
        kiro_agent = create_kiro_agent(
            agent_id=agent_id,
            name=name,
            description=desc,
            model=settings.default_model or "claude-sonnet-4.5",
            system_prompt=prompt,
        )
        kiro_agent.config.icon = icon
        agent_registry._agents[agent_id] = kiro_agent
        agent_registry._configs[agent_id] = kiro_agent.config
    
    agent_registry._default_id = "mo"
