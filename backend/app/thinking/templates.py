"""Thinking templates for task-specific reasoning patterns.

Provides structured templates that guide the AI's thinking process
for different types of tasks (code review, architecture, debugging, etc.)
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.thinking.models import ThinkingStepType, ThinkingLevel


class TemplateCategory(str, Enum):
    """Categories of thinking templates."""

    CODE = "code"
    ARCHITECTURE = "architecture"
    DEBUGGING = "debugging"
    ANALYSIS = "analysis"
    PLANNING = "planning"
    GENERAL = "general"


@dataclass
class ThinkingTemplate:
    """A template for structured thinking about a specific task type."""

    id: str
    name: str
    category: TemplateCategory
    description: str
    focus_areas: list[str]
    required_steps: list[ThinkingStepType]
    optional_steps: list[ThinkingStepType] = field(default_factory=list)
    min_level: ThinkingLevel = ThinkingLevel.LOW
    keywords: list[str] = field(default_factory=list)
    prompt_additions: str = ""

    def get_steps_for_level(self, level: ThinkingLevel) -> list[ThinkingStepType]:
        """Get the steps to use for a given thinking level."""
        if level == ThinkingLevel.OFF:
            return []

        # Always include required steps
        steps = list(self.required_steps)

        # Add optional steps based on level
        level_values = {
            ThinkingLevel.MINIMAL: 0,
            ThinkingLevel.LOW: 1,
            ThinkingLevel.MEDIUM: 2,
            ThinkingLevel.HIGH: 3,
            ThinkingLevel.MAX: 4,
        }
        current_level = level_values.get(level, 2)

        # Add more optional steps as level increases
        if self.optional_steps:
            optional_count = min(current_level, len(self.optional_steps))
            steps.extend(self.optional_steps[:optional_count])

        return steps

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category.value,
            "description": self.description,
            "focus_areas": self.focus_areas,
            "required_steps": [s.value for s in self.required_steps],
            "optional_steps": [s.value for s in self.optional_steps],
            "min_level": self.min_level.value,
            "keywords": self.keywords,
        }


# Built-in templates
TEMPLATES: dict[str, ThinkingTemplate] = {
    "code_review": ThinkingTemplate(
        id="code_review",
        name="Code Review",
        category=TemplateCategory.CODE,
        description="Systematic code review with security, performance, and maintainability checks",
        focus_areas=[
            "Security vulnerabilities (injection, XSS, auth issues)",
            "Performance bottlenecks and optimization opportunities",
            "Code maintainability and readability",
            "Error handling and edge cases",
            "Test coverage and testability",
        ],
        required_steps=[
            ThinkingStepType.ANALYSIS,
            ThinkingStepType.EVALUATION,
        ],
        optional_steps=[
            ThinkingStepType.RISK_ASSESSMENT,
            ThinkingStepType.VALIDATION,
            ThinkingStepType.CRITIQUE,
        ],
        min_level=ThinkingLevel.MEDIUM,
        keywords=["review", "code review", "check", "audit", "examine"],
        prompt_additions=(
            "When reviewing code, systematically check:\n"
            "1. Security: Look for injection points, auth bypass, data exposure\n"
            "2. Performance: Identify N+1 queries, unnecessary loops, memory leaks\n"
            "3. Maintainability: Check naming, structure, documentation\n"
            "4. Edge cases: Consider null, empty, boundary conditions\n"
        ),
    ),

    "architecture": ThinkingTemplate(
        id="architecture",
        name="Architecture Design",
        category=TemplateCategory.ARCHITECTURE,
        description="System architecture analysis with scalability, trade-offs, and implementation planning",
        focus_areas=[
            "Scalability and performance at scale",
            "System boundaries and interfaces",
            "Trade-offs between approaches",
            "Implementation complexity",
            "Future extensibility",
        ],
        required_steps=[
            ThinkingStepType.ANALYSIS,
            ThinkingStepType.EVALUATION,
            ThinkingStepType.DECISION,
        ],
        optional_steps=[
            ThinkingStepType.RISK_ASSESSMENT,
            ThinkingStepType.IMPLEMENTATION,
            ThinkingStepType.VALIDATION,
            ThinkingStepType.CRITIQUE,
        ],
        min_level=ThinkingLevel.HIGH,
        keywords=["architecture", "design", "system", "structure", "scale", "pattern"],
        prompt_additions=(
            "For architecture decisions, consider:\n"
            "1. Current requirements vs future growth\n"
            "2. Team capabilities and maintenance burden\n"
            "3. Integration with existing systems\n"
            "4. Cost and resource implications\n"
        ),
    ),

    "debugging": ThinkingTemplate(
        id="debugging",
        name="Debugging",
        category=TemplateCategory.DEBUGGING,
        description="Systematic debugging with root cause analysis and fix validation",
        focus_areas=[
            "Root cause identification",
            "Reproduction steps",
            "Impact assessment",
            "Fix validation",
            "Regression prevention",
        ],
        required_steps=[
            ThinkingStepType.ANALYSIS,
            ThinkingStepType.VALIDATION,
        ],
        optional_steps=[
            ThinkingStepType.RISK_ASSESSMENT,
            ThinkingStepType.IMPLEMENTATION,
            ThinkingStepType.CRITIQUE,
        ],
        min_level=ThinkingLevel.MEDIUM,
        keywords=["debug", "bug", "fix", "error", "issue", "problem", "broken", "crash"],
        prompt_additions=(
            "When debugging:\n"
            "1. Understand the expected vs actual behavior\n"
            "2. Identify the minimal reproduction case\n"
            "3. Trace the execution path to the root cause\n"
            "4. Consider why the bug wasn't caught earlier\n"
            "5. Verify the fix doesn't introduce new issues\n"
        ),
    ),

    "implementation": ThinkingTemplate(
        id="implementation",
        name="Implementation",
        category=TemplateCategory.CODE,
        description="Feature implementation with planning and validation",
        focus_areas=[
            "Requirements clarity",
            "Implementation approach",
            "Dependencies and impacts",
            "Testing strategy",
            "Documentation needs",
        ],
        required_steps=[
            ThinkingStepType.ANALYSIS,
            ThinkingStepType.DECISION,
            ThinkingStepType.IMPLEMENTATION,
        ],
        optional_steps=[
            ThinkingStepType.EVALUATION,
            ThinkingStepType.RISK_ASSESSMENT,
            ThinkingStepType.VALIDATION,
        ],
        min_level=ThinkingLevel.MEDIUM,
        keywords=["implement", "create", "build", "add", "develop", "write"],
        prompt_additions=(
            "For implementation:\n"
            "1. Clarify all requirements before starting\n"
            "2. Plan the approach and data structures\n"
            "3. Consider error handling and edge cases\n"
            "4. Plan for testing and documentation\n"
        ),
    ),

    "refactoring": ThinkingTemplate(
        id="refactoring",
        name="Refactoring",
        category=TemplateCategory.CODE,
        description="Code refactoring with safety and improvement validation",
        focus_areas=[
            "Current code problems",
            "Improvement goals",
            "Refactoring safety",
            "Backward compatibility",
            "Test coverage",
        ],
        required_steps=[
            ThinkingStepType.ANALYSIS,
            ThinkingStepType.EVALUATION,
            ThinkingStepType.VALIDATION,
        ],
        optional_steps=[
            ThinkingStepType.RISK_ASSESSMENT,
            ThinkingStepType.IMPLEMENTATION,
            ThinkingStepType.CRITIQUE,
        ],
        min_level=ThinkingLevel.MEDIUM,
        keywords=["refactor", "improve", "clean", "restructure", "reorganize"],
        prompt_additions=(
            "For refactoring:\n"
            "1. Identify what's wrong with current code\n"
            "2. Define clear improvement goals\n"
            "3. Ensure tests exist before changing\n"
            "4. Make small, incremental changes\n"
            "5. Verify behavior is preserved\n"
        ),
    ),

    "security_analysis": ThinkingTemplate(
        id="security_analysis",
        name="Security Analysis",
        category=TemplateCategory.ANALYSIS,
        description="Security-focused analysis of code or systems",
        focus_areas=[
            "Authentication and authorization",
            "Input validation and sanitization",
            "Data protection and encryption",
            "Injection vulnerabilities",
            "Security configuration",
        ],
        required_steps=[
            ThinkingStepType.ANALYSIS,
            ThinkingStepType.RISK_ASSESSMENT,
            ThinkingStepType.VALIDATION,
        ],
        optional_steps=[
            ThinkingStepType.EVALUATION,
            ThinkingStepType.CRITIQUE,
        ],
        min_level=ThinkingLevel.HIGH,
        keywords=["security", "vulnerability", "exploit", "auth", "injection", "xss"],
        prompt_additions=(
            "Security analysis checklist:\n"
            "1. OWASP Top 10 vulnerabilities\n"
            "2. Authentication/authorization flaws\n"
            "3. Sensitive data exposure\n"
            "4. Security misconfigurations\n"
            "5. Input validation gaps\n"
        ),
    ),

    "general": ThinkingTemplate(
        id="general",
        name="General Analysis",
        category=TemplateCategory.GENERAL,
        description="General-purpose thinking for unclassified tasks",
        focus_areas=[
            "Problem understanding",
            "Approach options",
            "Best solution selection",
        ],
        required_steps=[
            ThinkingStepType.ANALYSIS,
            ThinkingStepType.DECISION,
        ],
        optional_steps=[
            ThinkingStepType.EVALUATION,
            ThinkingStepType.VALIDATION,
            ThinkingStepType.CRITIQUE,
        ],
        min_level=ThinkingLevel.LOW,
        keywords=[],  # Fallback template
        prompt_additions="",
    ),
}


class ThinkingTemplates:
    """Manager for thinking templates."""

    def __init__(self):
        self._templates = dict(TEMPLATES)
        self._custom_templates: dict[str, ThinkingTemplate] = {}

    def get(self, template_id: str) -> ThinkingTemplate | None:
        """Get a template by ID."""
        return self._custom_templates.get(template_id) or self._templates.get(template_id)

    def get_all(self) -> list[ThinkingTemplate]:
        """Get all available templates."""
        all_templates = dict(self._templates)
        all_templates.update(self._custom_templates)
        return list(all_templates.values())

    def register(self, template: ThinkingTemplate) -> None:
        """Register a custom template."""
        self._custom_templates[template.id] = template

    def detect_template(self, message: str) -> ThinkingTemplate:
        """Detect the most appropriate template for a message.

        Args:
            message: The user's message

        Returns:
            Best matching ThinkingTemplate
        """
        message_lower = message.lower()
        best_match: ThinkingTemplate | None = None
        best_score = 0

        for template in self.get_all():
            if not template.keywords:
                continue

            score = sum(1 for kw in template.keywords if kw in message_lower)
            if score > best_score:
                best_score = score
                best_match = template

        return best_match or self._templates["general"]

    def get_by_category(self, category: TemplateCategory) -> list[ThinkingTemplate]:
        """Get all templates in a category."""
        return [t for t in self.get_all() if t.category == category]


# Global templates instance
_templates: ThinkingTemplates | None = None


def get_templates() -> ThinkingTemplates:
    """Get the global templates instance."""
    global _templates
    if _templates is None:
        _templates = ThinkingTemplates()
    return _templates


def get_template(template_id: str) -> ThinkingTemplate | None:
    """Get a template by ID."""
    return get_templates().get(template_id)


def detect_template(message: str) -> ThinkingTemplate:
    """Detect the appropriate template for a message."""
    return get_templates().detect_template(message)
