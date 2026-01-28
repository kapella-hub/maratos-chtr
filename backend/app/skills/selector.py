"""Skill Selector - Maps task types to skills deterministically.

The SkillSelector provides:
1. Deterministic mapping from task types to skills
2. Trigger-based skill detection from natural language
3. Fallback to Architect agent for complex/ambiguous tasks
4. Skill composition resolution
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from app.skills.schema import TaskType, SkillSchema

logger = logging.getLogger(__name__)


@dataclass
class SkillMatch:
    """Result of skill matching."""
    skill_id: str
    confidence: float  # 0.0 to 1.0
    task_type: TaskType | None = None
    matched_trigger: str | None = None
    requires_architect: bool = False  # If true, Architect should refine


@dataclass
class SkillSelection:
    """Result of skill selection for a task."""
    primary_skill: SkillMatch | None = None
    fallback_skills: list[SkillMatch] = field(default_factory=list)
    composition: list[str] = field(default_factory=list)  # Ordered skill IDs to compose
    requires_planning: bool = False  # If true, needs Architect planning first


# =============================================================================
# Task Type Detection Patterns
# =============================================================================

TASK_TYPE_PATTERNS: dict[TaskType, list[str]] = {
    TaskType.BOOTSTRAP_PROJECT: [
        r"create\s+(?:a\s+)?(?:new\s+)?(?:fastapi|flask|django|express|react|vue|next)",
        r"(?:fastapi|flask|django|express|react|vue|next)\s+project",
        r"bootstrap\s+(?:a\s+)?(?:new\s+)?(?:project|app|api|react|fastapi|django)",
        r"scaffold\s+(?:a\s+)?(?:new\s+)?(?:project|app)",
        r"start\s+(?:a\s+)?new\s+(?:project|app)",
        r"initialize\s+(?:a\s+)?(?:new\s+)?(?:project|repo)",
        r"build\s+me\s+a\s+(?:fastapi|react|django)",
        r"new\s+(?:fastapi|react|django|express)\s+(?:project|app)",
        r"create\s+(?:a\s+)?new\s+project",  # Generic "create a new project"
    ],
    TaskType.ADD_API_ENDPOINT: [
        r"add\s+(?:an?\s+)?(?:api\s+)?endpoint",
        r"create\s+(?:an?\s+)?(?:rest\s+)?(?:api\s+)?route",
        r"implement\s+(?:the\s+)?(?:api\s+)?endpoint",
        r"add\s+(?:a\s+)?(?:get|post|put|delete|patch)\s+(?:endpoint|route)",
    ],
    TaskType.ADD_UI_COMPONENT: [
        r"add\s+(?:a\s+)?(?:react\s+)?component",
        r"create\s+(?:a\s+)?(?:ui\s+)?component",
        r"build\s+(?:a\s+)?(?:new\s+)?(?:ui\s+)?component",
        r"implement\s+(?:the\s+)?(?:ui\s+for|component)",
    ],
    TaskType.DOCKERIZE: [
        r"docker(?:ize)?",
        r"add\s+(?:a\s+)?dockerfile",
        r"containerize",
        r"add\s+docker\s*compose",
        r"create\s+(?:a\s+)?docker\s+(?:setup|config)",
        r"with\s+docker",
    ],
    TaskType.ADD_CI: [
        r"add\s+(?:a\s+)?ci(?:/cd)?(?:\s+pipeline)?",
        r"setup\s+(?:github\s+)?actions",
        r"create\s+(?:a\s+)?(?:ci\s+)?pipeline",
        r"add\s+(?:gitlab\s+)?ci",
        r"(?:setup|add)\s+continuous\s+integration",
        r"with\s+ci",
    ],
    TaskType.ADD_DATABASE: [
        r"add\s+(?:a\s+)?database",
        r"setup\s+(?:the\s+)?database",
        r"add\s+(?:db\s+)?migration",
        r"create\s+(?:the\s+)?(?:db\s+)?schema",
        r"add\s+(?:sqlalchemy|prisma|alembic)",
    ],
    TaskType.ADD_AUTH: [
        r"add\s+(?:user\s+)?auth(?:entication)?",
        r"implement\s+(?:user\s+)?login",
        r"add\s+(?:jwt|oauth|session)\s+auth",
        r"setup\s+(?:user\s+)?authentication",
    ],
    TaskType.SECURITY_REVIEW: [
        r"security\s+(?:review|audit|scan)",
        r"check\s+(?:for\s+)?(?:security\s+)?vulnerabilities",
        r"run\s+(?:a\s+)?security\s+(?:check|scan)",
        r"audit\s+(?:the\s+)?(?:code|security)",
    ],
    TaskType.DOCUMENTATION: [
        r"(?:add|create|write)\s+(?:the\s+)?(?:api\s+)?documentation",
        r"(?:add|create|write)\s+(?:the\s+)?readme",
        r"(?:add|generate)\s+(?:the\s+)?(?:api\s+)?docs",
        r"document\s+(?:the\s+)?(?:api|code|project)",
        r"(?:add|create)\s+(?:the\s+)?changelog",
    ],
    TaskType.REFACTOR: [
        r"refactor\s+(?:the\s+)?(?:code|module|function)",
        r"clean\s*up\s+(?:the\s+)?code",
        r"improve\s+(?:the\s+)?(?:code\s+)?(?:quality|structure)",
        r"restructure\s+(?:the\s+)?(?:code|module)",
    ],
    TaskType.TEST: [
        r"(?:add|write|create)\s+(?:the\s+)?tests",
        r"(?:add|increase)\s+(?:test\s+)?coverage",
        r"implement\s+(?:the\s+)?(?:unit|integration)\s+tests",
        r"test\s+(?:the\s+)?(?:code|module|function)",
    ],
    TaskType.BUILD: [
        r"build\s+(?:the\s+)?(?:project|app)",
        r"compile\s+(?:the\s+)?(?:project|code)",
        r"create\s+(?:a\s+)?(?:production\s+)?build",
        r"bundle\s+(?:the\s+)?(?:app|assets)",
    ],
    TaskType.DEPLOY: [
        r"deploy\s+(?:to\s+)?(?:production|staging)",
        r"setup\s+(?:the\s+)?deployment",
        r"(?:add|create)\s+(?:the\s+)?deployment\s+(?:config|scripts)",
        r"push\s+to\s+(?:production|staging)",
    ],
}


# =============================================================================
# Skill Mapping
# =============================================================================

# Maps task types to skill IDs (deterministic mapping)
TASK_TYPE_TO_SKILL: dict[TaskType, str] = {
    TaskType.BOOTSTRAP_PROJECT: "app-factory",  # Meta-skill handles all bootstrap
    TaskType.ADD_API_ENDPOINT: "add-api-endpoint",
    TaskType.ADD_UI_COMPONENT: "add-ui-component",
    TaskType.DOCKERIZE: "dockerize-and-compose",
    TaskType.ADD_CI: "add-ci-pipeline",
    TaskType.ADD_DATABASE: "add-db-migration",
    TaskType.ADD_AUTH: "add-auth",
    TaskType.SECURITY_REVIEW: "security-review",
    TaskType.DOCUMENTATION: "docs-release-notes",
    TaskType.REFACTOR: "refactor",
    TaskType.TEST: "add-tests",
    TaskType.BUILD: "build-project",
    TaskType.DEPLOY: "deploy-project",
}


# Framework-specific skill variants
FRAMEWORK_SKILLS: dict[str, dict[str, str]] = {
    "fastapi": {
        "bootstrap": "project-bootstrap-fastapi",
        "endpoint": "fastapi-endpoint",
    },
    "react": {
        "bootstrap": "project-bootstrap-react",
        "component": "react-component",
    },
    "express": {
        "bootstrap": "project-bootstrap-express",
    },
    "vue": {
        "bootstrap": "project-bootstrap-vue",
    },
    "django": {
        "bootstrap": "project-bootstrap-django",
    },
}


class SkillSelector:
    """Selects appropriate skills for tasks deterministically."""

    def __init__(self) -> None:
        self._skill_cache: dict[str, SkillSchema] = {}
        self._custom_mappings: dict[TaskType, str] = {}

    def register_skill(self, skill: SkillSchema) -> None:
        """Register a skill for selection."""
        self._skill_cache[skill.id] = skill

    def add_mapping(self, task_type: TaskType, skill_id: str) -> None:
        """Add a custom task type to skill mapping."""
        self._custom_mappings[task_type] = skill_id

    def detect_task_type(self, prompt: str) -> TaskType | None:
        """Detect task type from natural language prompt.

        Returns the most confident task type match, or None if ambiguous.
        Uses priority ordering: BOOTSTRAP_PROJECT takes precedence.
        """
        prompt_lower = prompt.lower()
        matches: list[tuple[TaskType, int, int]] = []

        # Priority ordering - lower number = higher priority
        priority_order = {
            TaskType.BOOTSTRAP_PROJECT: 1,
            TaskType.ADD_FEATURE: 2,
            TaskType.ADD_API_ENDPOINT: 3,
            TaskType.ADD_UI_COMPONENT: 3,
            TaskType.DOCKERIZE: 5,
            TaskType.ADD_CI: 5,
            TaskType.ADD_DATABASE: 4,
            TaskType.ADD_AUTH: 4,
            TaskType.SECURITY_REVIEW: 6,
            TaskType.DOCUMENTATION: 6,
            TaskType.REFACTOR: 4,
            TaskType.TEST: 4,
            TaskType.BUILD: 5,
            TaskType.DEPLOY: 5,
        }

        for task_type, patterns in TASK_TYPE_PATTERNS.items():
            for pattern in patterns:
                match = re.search(pattern, prompt_lower)
                if match:
                    # Count matches and get priority
                    match_count = len(re.findall(pattern, prompt_lower))
                    priority = priority_order.get(task_type, 10)
                    matches.append((task_type, priority, match_count))
                    break

        if not matches:
            return None

        # Sort by priority first (lower = higher priority), then by match count
        matches.sort(key=lambda x: (x[1], -x[2]))
        return matches[0][0]

    def detect_framework(self, prompt: str) -> str | None:
        """Detect framework from prompt."""
        prompt_lower = prompt.lower()

        framework_patterns = {
            "fastapi": r"fastapi|fast\s*api",
            "react": r"react(?:\.?js)?|next\.?js",
            "vue": r"vue(?:\.?js)?|nuxt",
            "express": r"express(?:\.?js)?|node\.?js\s+api",
            "django": r"django",
            "flask": r"flask",
        }

        for framework, pattern in framework_patterns.items():
            if re.search(pattern, prompt_lower):
                return framework

        return None

    def select(self, prompt: str, context: dict[str, Any] | None = None) -> SkillSelection:
        """Select skill(s) for a given prompt.

        This is the main entry point for skill selection. It:
        1. Detects task type from prompt
        2. Maps task type to skill ID
        3. Detects framework for variants
        4. Resolves skill composition
        5. Falls back to Architect if needed

        Args:
            prompt: Natural language task description
            context: Optional context with project info

        Returns:
            SkillSelection with primary skill and any composition needed
        """
        context = context or {}

        # Detect task type
        task_type = self.detect_task_type(prompt)
        framework = self.detect_framework(prompt)

        if task_type is None:
            # Ambiguous - needs Architect planning
            return SkillSelection(
                requires_planning=True,
                primary_skill=SkillMatch(
                    skill_id="",
                    confidence=0.0,
                    requires_architect=True,
                ),
            )

        # Get skill ID from mapping
        skill_id = self._custom_mappings.get(task_type) or TASK_TYPE_TO_SKILL.get(task_type)

        if not skill_id:
            return SkillSelection(requires_planning=True)

        # Check for framework-specific variant
        if framework and framework in FRAMEWORK_SKILLS:
            variants = FRAMEWORK_SKILLS[framework]

            # Map task type to variant key
            variant_key = None
            if task_type == TaskType.BOOTSTRAP_PROJECT:
                variant_key = "bootstrap"
            elif task_type == TaskType.ADD_API_ENDPOINT:
                variant_key = "endpoint"
            elif task_type == TaskType.ADD_UI_COMPONENT:
                variant_key = "component"

            if variant_key and variant_key in variants:
                skill_id = variants[variant_key]

        # Build primary match
        primary = SkillMatch(
            skill_id=skill_id,
            confidence=0.9 if task_type else 0.5,
            task_type=task_type,
        )

        # Check if this is a complex request needing composition
        composition = self._detect_composition(prompt, task_type, framework)

        return SkillSelection(
            primary_skill=primary,
            composition=composition,
            requires_planning=len(composition) > 3,  # Complex compositions need planning
        )

    def _detect_composition(
        self,
        prompt: str,
        task_type: TaskType | None,
        framework: str | None,
    ) -> list[str]:
        """Detect if prompt requires multiple skills (composition)."""
        composition = []
        prompt_lower = prompt.lower()

        # Check for composition indicators
        composition_patterns = [
            (r"(?:with|and)\s+docker(?:\s+compose)?", "dockerize-and-compose"),
            (r"(?:with|,\s*|and\s+)ci(?:/cd)?", "add-ci-pipeline"),  # "with CI", ", CI", "and CI"
            (r"docker\s*compose\s+and\s+ci", "add-ci-pipeline"),  # After docker
            (r"(?:with|and)\s+tests?", "add-tests"),
            (r"(?:with|and)\s+auth(?:entication)?", "add-auth"),
            (r"(?:with|and)\s+database", "add-db-migration"),
            (r"(?:and\s+)?(?:run\s+)?security\s+review", "security-review"),
        ]

        for pattern, skill_id in composition_patterns:
            if re.search(pattern, prompt_lower) and skill_id not in composition:
                composition.append(skill_id)

        # For bootstrap, add the primary bootstrap skill first
        if task_type == TaskType.BOOTSTRAP_PROJECT and framework:
            variant_skills = FRAMEWORK_SKILLS.get(framework, {})
            if "bootstrap" in variant_skills:
                composition.insert(0, variant_skills["bootstrap"])

        return composition

    def get_skill_for_task(
        self,
        task_description: str,
        agent_id: str | None = None,
    ) -> str | None:
        """Get skill ID for a task description.

        Simple lookup that can be used by the orchestration engine.
        """
        selection = self.select(task_description)

        if selection.primary_skill and selection.primary_skill.skill_id:
            return selection.primary_skill.skill_id

        return None

    def get_composition_for_request(self, prompt: str) -> list[str]:
        """Get ordered list of skills needed to fulfill a request."""
        selection = self.select(prompt)
        return selection.composition or (
            [selection.primary_skill.skill_id]
            if selection.primary_skill and selection.primary_skill.skill_id
            else []
        )


# =============================================================================
# Global Selector Instance
# =============================================================================

skill_selector = SkillSelector()


def get_skill_selector() -> SkillSelector:
    """Get the global skill selector instance."""
    return skill_selector
