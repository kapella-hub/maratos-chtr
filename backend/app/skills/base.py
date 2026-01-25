"""Base skill interface for MaratOS."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import yaml


@dataclass
class SkillStep:
    """A step in a skill workflow."""
    
    name: str
    action: str  # kiro_architect, kiro_validate, kiro_test, shell, filesystem
    description: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    condition: str | None = None  # Optional condition to run this step


@dataclass
class Skill:
    """A skill definition that can be executed by agents via Kiro."""
    
    id: str
    name: str
    description: str
    version: str = "1.0.0"
    
    # When to use this skill
    triggers: list[str] = field(default_factory=list)  # Keywords that trigger this skill
    
    # Kiro-compatible workflow
    workflow: list[SkillStep] = field(default_factory=list)
    
    # Context/prompts for Kiro
    system_context: str = ""  # Added to Kiro prompts
    quality_checklist: list[str] = field(default_factory=list)  # Validation points
    test_requirements: list[str] = field(default_factory=list)  # Test generation guidance
    
    # Metadata
    author: str = ""
    tags: list[str] = field(default_factory=list)
    path: Path | None = None
    
    def to_kiro_context(self) -> str:
        """Generate context to add to Kiro prompts."""
        parts = []
        
        if self.system_context:
            parts.append(f"## Skill: {self.name}\n{self.system_context}")
        
        if self.quality_checklist:
            parts.append("## Quality Checklist")
            for item in self.quality_checklist:
                parts.append(f"- {item}")
        
        if self.test_requirements:
            parts.append("## Test Requirements")
            for item in self.test_requirements:
                parts.append(f"- {item}")
        
        return "\n\n".join(parts)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "triggers": self.triggers,
            "tags": self.tags,
            "workflow_steps": len(self.workflow),
        }
    
    @classmethod
    def from_yaml(cls, path: Path) -> "Skill":
        """Load skill from YAML file."""
        with open(path) as f:
            data = yaml.safe_load(f)
        
        workflow = []
        for step_data in data.get("workflow", []):
            workflow.append(SkillStep(
                name=step_data.get("name", ""),
                action=step_data.get("action", ""),
                description=step_data.get("description", ""),
                params=step_data.get("params", {}),
                condition=step_data.get("condition"),
            ))
        
        return cls(
            id=data.get("id", path.stem),
            name=data.get("name", path.stem),
            description=data.get("description", ""),
            version=data.get("version", "1.0.0"),
            triggers=data.get("triggers", []),
            workflow=workflow,
            system_context=data.get("system_context", ""),
            quality_checklist=data.get("quality_checklist", []),
            test_requirements=data.get("test_requirements", []),
            author=data.get("author", ""),
            tags=data.get("tags", []),
            path=path,
        )


class SkillRegistry:
    """Registry for managing skills."""
    
    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}
    
    def register(self, skill: Skill) -> None:
        """Register a skill."""
        self._skills[skill.id] = skill
    
    def get(self, skill_id: str) -> Skill | None:
        """Get a skill by ID."""
        return self._skills.get(skill_id)
    
    def find_by_trigger(self, text: str) -> list[Skill]:
        """Find skills that match trigger keywords in text."""
        text_lower = text.lower()
        matches = []
        for skill in self._skills.values():
            for trigger in skill.triggers:
                if trigger.lower() in text_lower:
                    matches.append(skill)
                    break
        return matches
    
    def list_all(self) -> list[dict[str, Any]]:
        """List all skills."""
        return [s.to_dict() for s in self._skills.values()]
    
    def search(self, query: str) -> list[Skill]:
        """Search skills by name, description, or tags."""
        query_lower = query.lower()
        matches = []
        for skill in self._skills.values():
            if (query_lower in skill.name.lower() or
                query_lower in skill.description.lower() or
                any(query_lower in tag.lower() for tag in skill.tags)):
                matches.append(skill)
        return matches


# Global registry
skill_registry = SkillRegistry()
