"""Architect Agent - Uses Kiro with architecture-focused prompts."""

from typing import Any

from app.agents.base import Agent, AgentConfig
from app.agents.tool_contract import get_full_tool_section
from app.agents.diagram_instructions import get_diagram_instructions
from app.prompts import get_prompt


# Thinking level instructions - appended based on settings.thinking_level
THINKING_INSTRUCTIONS = {
    "off": """
## Thinking Mode: OFF
Skip analysis. Immediately spawn coders for the requested tasks.
""",
    "minimal": """
## Thinking Mode: MINIMAL
Quick sanity check only:
- Is the request clear?
- Do the files exist?
Then spawn coders.
""",
    "low": """
## Thinking Mode: LOW
Brief analysis (1-2 paragraphs):
- What files need to change?
- Any obvious dependencies?
Then spawn coders with your findings.
""",
    "medium": """
## Thinking Mode: MEDIUM
Structured analysis:
1. **Problem**: What exactly needs to be done?
2. **Files**: Which files need modification?
3. **Approach**: How should it be implemented?
4. **Risks**: Any potential issues?

Then spawn coders with detailed context.
""",
    "high": """
## Thinking Mode: HIGH
Deep analysis before spawning:

### 1. Problem Analysis
- Break down the request into sub-problems
- Identify implicit requirements

### 2. Codebase Research
- Read relevant files thoroughly
- Understand existing patterns and conventions
- Note any related functionality

### 3. Approach Comparison
Consider 2-3 approaches:
| Approach | Pros | Cons |
|----------|------|------|
| A | ... | ... |
| B | ... | ... |

### 4. Risk Assessment
- What could go wrong?
- Edge cases to handle?
- Breaking changes?

### 5. Implementation Plan
Spawn coders with comprehensive context from your analysis.
""",
    "max": """
## Thinking Mode: MAX (Exhaustive)
Perform exhaustive analysis with self-critique:

### Phase 1: Deep Understanding
- Read ALL relevant files, not just obvious ones
- Map the full dependency graph
- Understand the historical context (git history if available)

### Phase 2: Requirements Extraction
- Explicit requirements from the request
- Implicit requirements (security, performance, UX)
- Non-functional requirements

### Phase 3: Multi-Approach Analysis
Evaluate 3+ approaches:
| Approach | Pros | Cons | Effort | Risk |
|----------|------|------|--------|------|
| A | ... | ... | ... | ... |
| B | ... | ... | ... | ... |
| C | ... | ... | ... | ... |

### Phase 4: Self-Critique
**Challenge your own plan:**
- What assumptions am I making?
- What could I be missing?
- If this fails, why would it fail?
- Am I over-engineering? Under-engineering?

### Phase 5: Risk Mitigation
- Identify top 3 risks
- Plan mitigation for each
- Define rollback strategy

### Phase 6: Detailed Implementation Plan
Spawn coders with:
- Comprehensive context
- Specific implementation notes
- Test cases to verify
- Acceptance criteria
""",
}


class ArchitectAgent(Agent):
    """Architect agent for complex design work via Kiro."""

    def __init__(self) -> None:
        # Load system prompt from yaml
        base_prompt = get_prompt("agent_prompts.architect")

        # Inject tool section and diagram instructions into prompt
        tool_section = get_full_tool_section("architect")
        diagram_instructions = get_diagram_instructions()
        prompt = base_prompt.format(
            tool_section=tool_section,
            diagram_instructions=diagram_instructions,
        )

        super().__init__(
            AgentConfig(
                id="architect",
                name="Architect",
                description="System design and complex architecture via Kiro",
                icon="🏗️",
                model="",  # Inherit from settings
                temperature=0.5,  # Higher for exploring multiple design alternatives
                system_prompt=prompt,
                tools=["filesystem", "shell", "kiro"],
            )
        )

    def get_system_prompt(self, context: dict[str, Any] | None = None) -> tuple[str, list]:
        """Build system prompt with context and thinking level."""
        prompt, matched_skills = super().get_system_prompt(context)

        # Add thinking level instructions
        from app.config import settings
        thinking_level = context.get("thinking_level") if context else None
        thinking_level = thinking_level or settings.thinking_level or "medium"

        if thinking_level in THINKING_INSTRUCTIONS:
            prompt += "\n" + THINKING_INSTRUCTIONS[thinking_level]

        if context:
            if "workspace" in context:
                prompt += f"\n\n## Workspace\n`{context['workspace']}`\n"
            if "project" in context:
                prompt += f"\n\n## Project Context\n{context['project']}\n"

        return prompt, matched_skills
