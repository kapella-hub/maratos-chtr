"""Agent Swarms & Squads Module ("The Council").

This module implements the "Phase 18" Swarm Intelligence architecture.
It allows for:
1. Dynamic Squad Selection based on user prompt.
2. Parallel Brainstorming (Map-Reduce style).
3. Consolidated "RFC" style output for the Architect to ingest.
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import AsyncIterator, List, Dict, Any

from app.autonomous.engine import EngineEventType, EngineEvent
from app.agents.registry import agent_registry

logger = logging.getLogger(__name__)


@dataclass
class SpecialistAgent:
    """A dynamically configured specialist agent."""
    role: str       # e.g., "frontend_specialist"
    description: str
    focus_area: str # e.g., "UI/UX, Components, Tailwind"


@dataclass
class BrainstormResult:
    """The output of a brainstorming session."""
    specialist_role: str
    rfc_content: str  # The "Request for Comments" checking document
    timestamp: str


class SquadFactory:
    """Factory for assembling agent squads based on task complexity."""

    @staticmethod
    def analyze_task_complexity(prompt: str) -> bool:
        """Heuristic to decide if Swarm is needed."""
        # Simple keyword heuristic for V1
        # In V2, we can ask an LLM classifier
        complex_keywords = [
            "distributed", "system", "platform", "microservices",
            "full-stack", "full stack", "architecture", "design",
            "mvp", "from scratch", "create a", "build a", "traceloom"
        ]
        prompt_lower = prompt.lower()
        return any(k in prompt_lower for k in complex_keywords) and len(prompt.split()) > 10

    @staticmethod
    def assemble_squad(prompt: str) -> List[SpecialistAgent]:
        """Select appropriate specialists for the task."""
        # For V1, we use a standard "Full Stack Squad" if complexity is high.
        # Future: Use LLM to pick roles dynamically.
        
        squad = []

        # Frontend Specialist
        if any(k in prompt.lower() for k in ["ui", "frontend", "react", "next", "web", "interface", "app", "view"]):
            squad.append(SpecialistAgent(
                role="frontend_architect",
                description="Expert in modern web frameworks (Next.js, React), UI/UX patterns, and CSS architecture.",
                focus_area="Frontend Architecture, Component Hierarchy, State Management, UI/UX"
            ))

        # Backend/Database Specialist
        if any(k in prompt.lower() for k in ["api", "backend", "db", "database", "sql", "server", "data", "model"]):
            squad.append(SpecialistAgent(
                role="backend_architect",
                description="Expert in API design (REST/GraphQL), Database Schema (SQL/NoSQL), and System Performance.",
                focus_area="API Routes, Database Schema, Data Models, Backend Logic"
            ))

        # DevOps/Systems Specialist (Only for very complex tasks)
        if any(k in prompt.lower() for k in ["deploy", "cloud", "docker", "ci/cd", "pipeline", "infrastructure"]):
             squad.append(SpecialistAgent(
                role="systems_architect",
                description="Expert in Infrastructure as Code, Deployment Pipelines, Docker, and Cloud Security.",
                focus_area="Deployment, Docker, CI/CD, Security, Infrastructure"
            ))
            
        # Fallback: if no specific keywords but complex, give Full Stack duo
        if not squad:
            squad = [
                SpecialistAgent(
                    role="frontend_architect",
                    description="Expert in modern web frameworks.",
                    focus_area="Frontend & UI"
                ),
                SpecialistAgent(
                    role="backend_architect",
                    description="Expert in backend systems and databases.",
                    focus_area="Backend & Data"
                )
            ]

        return squad


class BrainstormingSession:
    """Manages the parallel brainstorming process."""

    def __init__(self, run_id: str, prompt: str, workspace_path: str | None):
        self.run_id = run_id
        self.prompt = prompt
        self.workspace_path = workspace_path
        self.results: List[BrainstormResult] = []

    async def run(self) -> AsyncIterator[EngineEvent]:
        """Execute the brainstorming session."""
        
        # 1. Assemble Squad
        squad = SquadFactory.assemble_squad(self.prompt)
        if not squad:
            logger.info("Task too simple for swarm. Skipping.")
            return

        yield EngineEvent(
            type=EngineEventType.BRAINSTORMING_STARTED,
            run_id=self.run_id,
            data={"squad_size": len(squad), "roles": [a.role for a in squad]}
        )

        # 2. Parallel Execution
        # We use the generic 'architect' agent but with different system prompts per role
        base_architect = agent_registry.get("architect")
        if not base_architect:
            logger.error("Architect agent missing for brainstorming.")
            return

        tasks = []
        for specialist in squad:
            tasks.append(self._consult_specialist(base_architect, specialist))

        # Run all specialists in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 3. Collect Results
        for res in results:
            if isinstance(res, BrainstormResult):
                self.results.append(res)
                yield EngineEvent(
                    type=EngineEventType.BRAINSTORMING_PROGRESS,
                    run_id=self.run_id,
                    data={"role": res.specialist_role, "summary": res.rfc_content[:100] + "..."}
                )
            elif isinstance(res, Exception):
                logger.error(f"Specialist failed: {res}")

        # 4. Final Event
        yield EngineEvent(
            type=EngineEventType.BRAINSTORMING_COMPLETED,
            run_id=self.run_id,
            data={
                "rfcs": [
                    {"role": r.specialist_role, "content": r.rfc_content}
                    for r in self.results
                ]
            }
        )

    async def _consult_specialist(self, agent, specialist: SpecialistAgent) -> BrainstormResult:
        """Run a single specialist consultation."""
        
        system_prompt = f"""You are acting as the **{specialist.role}**.
{specialist.description}

Your Goal: Analyze the user's request specifically from your focus area: **{specialist.focus_area}**.

Create a "Mini-RFC" (Request for Comments) that outlines:
1. High-level architectural decisions for your domain.
2. Key technologies/libraries you recommend.
3. Potential pitfalls or risks.
4. A rough component/module breakdown.

Keep it concise but technical. Focus ONLY on your domain.
"""
        
        user_prompt = f"""
REQUEST: {self.prompt}

WORKSPACE: {self.workspace_path or 'New Project'}

Please provide your {specialist.role} RFC analysis.
"""

        response_text = ""
        # We treat this as a single-turn chat for now
        async for chunk in agent.chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            context={"workspace": self.workspace_path},
            model_override=None # Uses default (Sonnet)
        ):
            response_text += chunk

        return BrainstormResult(
            specialist_role=specialist.role,
            rfc_content=response_text,
            timestamp=""
        )
