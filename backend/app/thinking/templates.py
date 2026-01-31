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


# Templates are now loaded from YAML files in the templates/ directory


class ThinkingTemplates:
    """Manager for thinking templates."""

    def __init__(self):
        self._templates: dict[str, ThinkingTemplate] = {}
        self._custom_templates: dict[str, ThinkingTemplate] = {}
        self._load_templates()

    def _load_templates(self):
        """Load templates from YAML files."""
        import yaml
        import os
        from pathlib import Path

        # Define template directories
        base_dir = Path(__file__).parent / "templates"
        
        # Load built-in templates
        if base_dir.exists():
            for file_path in base_dir.glob("*.yaml"):
                try:
                    with open(file_path, "r") as f:
                        data = yaml.safe_load(f)
                        if self._validate_template_data(data):
                            template = self._create_template_from_dict(data)
                            self._templates[template.id] = template
                        else:
                            print(f"Invalid template data in {file_path}")
                except Exception as e:
                    print(f"Error loading template {file_path}: {e}")

        # Ensure general template exists as fallback
        if "general" not in self._templates:
            self._templates["general"] = ThinkingTemplate(
                id="general",
                name="General Analysis",
                category=TemplateCategory.GENERAL,
                description="General-purpose thinking for unclassified tasks",
                focus_areas=["Problem understanding", "Approach options", "Solution selection"],
                required_steps=[ThinkingStepType.ANALYSIS, ThinkingStepType.DECISION],
                optional_steps=[],
                min_level=ThinkingLevel.LOW,
                keywords=[],
                prompt_additions=""
            )

    def _validate_template_data(self, data: dict) -> bool:
        """Validate template dictionary structure."""
        required_fields = ["id", "name", "category", "description", "focus_areas", "required_steps"]
        return all(field in data for field in required_fields)

    def _create_template_from_dict(self, data: dict) -> ThinkingTemplate:
        """Create a ThinkingTemplate object from dictionary."""
        # Convert string values to enums
        category = TemplateCategory(data["category"])
        
        required_steps = []
        for step_str in data["required_steps"]:
            try:
                required_steps.append(ThinkingStepType(step_str.lower()))
            except ValueError:
                pass # Skip invalid steps
                
        optional_steps = []
        if "optional_steps" in data:
            for step_str in data["optional_steps"]:
                try:
                    optional_steps.append(ThinkingStepType(step_str.lower()))
                except ValueError:
                    pass

        min_level = ThinkingLevel(data.get("min_level", "medium").lower())

        return ThinkingTemplate(
            id=data["id"],
            name=data["name"],
            category=category,
            description=data["description"],
            focus_areas=data["focus_areas"],
            required_steps=required_steps,
            optional_steps=optional_steps,
            min_level=min_level,
            keywords=data.get("keywords", []),
            prompt_additions=data.get("prompt_additions", "")
        )

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
