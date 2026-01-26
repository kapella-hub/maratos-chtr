"""Skill loader for MaratOS with validation."""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from app.skills.base import Skill, skill_registry

logger = logging.getLogger(__name__)


@dataclass
class SkillValidationError:
    """A validation error in a skill file."""
    field: str
    message: str
    severity: str = "error"  # error, warning


@dataclass
class SkillValidationResult:
    """Result of skill validation."""
    path: Path
    skill_id: str | None = None
    valid: bool = False
    errors: list[SkillValidationError] = field(default_factory=list)
    warnings: list[SkillValidationError] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "skill_id": self.skill_id,
            "valid": self.valid,
            "errors": [{"field": e.field, "message": e.message} for e in self.errors],
            "warnings": [{"field": w.field, "message": w.message} for w in self.warnings],
        }


# Required fields for skill YAML
REQUIRED_FIELDS = ["id", "name", "description"]
VALID_ACTIONS = ["kiro_architect", "kiro_validate", "kiro_test", "kiro_prompt", "shell", "filesystem"]


def validate_skill_yaml(path: Path) -> SkillValidationResult:
    """Validate a skill YAML file.

    Returns validation result with errors and warnings.
    """
    result = SkillValidationResult(path=path)

    try:
        with open(path) as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        result.errors.append(SkillValidationError(
            field="yaml",
            message=f"Invalid YAML syntax: {e}"
        ))
        return result
    except Exception as e:
        result.errors.append(SkillValidationError(
            field="file",
            message=f"Could not read file: {e}"
        ))
        return result

    if not isinstance(data, dict):
        result.errors.append(SkillValidationError(
            field="root",
            message="Skill file must be a YAML object/dictionary"
        ))
        return result

    result.skill_id = data.get("id", path.stem)

    # Check required fields
    for field_name in REQUIRED_FIELDS:
        if not data.get(field_name):
            result.errors.append(SkillValidationError(
                field=field_name,
                message=f"Required field '{field_name}' is missing or empty"
            ))

    # Validate triggers
    triggers = data.get("triggers", [])
    if not triggers:
        result.warnings.append(SkillValidationError(
            field="triggers",
            message="No triggers defined - skill won't be auto-detected",
            severity="warning"
        ))
    elif not isinstance(triggers, list):
        result.errors.append(SkillValidationError(
            field="triggers",
            message="Triggers must be a list of strings"
        ))

    # Validate workflow
    workflow = data.get("workflow", [])
    if not workflow:
        result.warnings.append(SkillValidationError(
            field="workflow",
            message="No workflow steps defined",
            severity="warning"
        ))
    elif isinstance(workflow, list):
        for i, step in enumerate(workflow):
            if not isinstance(step, dict):
                result.errors.append(SkillValidationError(
                    field=f"workflow[{i}]",
                    message="Workflow step must be an object"
                ))
                continue

            if not step.get("name"):
                result.errors.append(SkillValidationError(
                    field=f"workflow[{i}].name",
                    message="Workflow step missing 'name'"
                ))

            action = step.get("action")
            if not action:
                result.errors.append(SkillValidationError(
                    field=f"workflow[{i}].action",
                    message="Workflow step missing 'action'"
                ))
            elif action not in VALID_ACTIONS:
                result.warnings.append(SkillValidationError(
                    field=f"workflow[{i}].action",
                    message=f"Unknown action '{action}'. Valid: {', '.join(VALID_ACTIONS)}",
                    severity="warning"
                ))

    # Validate quality_checklist
    checklist = data.get("quality_checklist", [])
    if checklist and not isinstance(checklist, list):
        result.errors.append(SkillValidationError(
            field="quality_checklist",
            message="quality_checklist must be a list of strings"
        ))

    # Validate test_requirements
    test_reqs = data.get("test_requirements", [])
    if test_reqs and not isinstance(test_reqs, list):
        result.errors.append(SkillValidationError(
            field="test_requirements",
            message="test_requirements must be a list of strings"
        ))

    # Set validity based on errors
    result.valid = len(result.errors) == 0

    return result


def load_skills_from_dir(skills_dir: Path) -> int:
    """Load all skills from a directory.

    Returns the number of skills loaded.
    """
    if not skills_dir.exists():
        logger.info(f"Skills directory does not exist: {skills_dir}")
        return 0

    count = 0
    for ext in ["*.yaml", "*.yml"]:
        for path in skills_dir.glob(f"**/{ext}"):
            # Validate first
            validation = validate_skill_yaml(path)
            if not validation.valid:
                for error in validation.errors:
                    logger.error(f"Skill {path}: {error.field} - {error.message}")
                continue

            for warning in validation.warnings:
                logger.warning(f"Skill {path}: {warning.field} - {warning.message}")

            try:
                skill = Skill.from_yaml(path)
                skill_registry.register(skill)
                logger.info(f"Loaded skill: {skill.id} from {path}")
                count += 1
            except Exception as e:
                logger.error(f"Failed to load skill from {path}: {e}")

    return count


def validate_all_skills(skills_dir: Path) -> list[SkillValidationResult]:
    """Validate all skills in a directory without loading them.

    Returns list of validation results for all skill files.
    """
    results = []

    if not skills_dir.exists():
        return results

    for ext in ["*.yaml", "*.yml"]:
        for path in skills_dir.glob(f"**/{ext}"):
            result = validate_skill_yaml(path)
            results.append(result)

    return results


# Track loaded skills validation results
_validation_results: list[SkillValidationResult] = []


def get_validation_results() -> list[SkillValidationResult]:
    """Get validation results from last skill load."""
    return _validation_results


def load_skills_with_validation(skills_dir: Path) -> tuple[int, list[SkillValidationResult]]:
    """Load skills and return validation results.

    Returns tuple of (skills_loaded, validation_results).
    """
    global _validation_results
    _validation_results = []

    if not skills_dir.exists():
        logger.info(f"Skills directory does not exist: {skills_dir}")
        return 0, []

    count = 0
    for ext in ["*.yaml", "*.yml"]:
        for path in skills_dir.glob(f"**/{ext}"):
            validation = validate_skill_yaml(path)
            _validation_results.append(validation)

            if not validation.valid:
                for error in validation.errors:
                    logger.error(f"Skill {path}: {error.field} - {error.message}")
                continue

            for warning in validation.warnings:
                logger.warning(f"Skill {path}: {warning.field} - {warning.message}")

            try:
                skill = Skill.from_yaml(path)
                skill_registry.register(skill)
                logger.info(f"Loaded skill: {skill.id} from {path}")
                count += 1
            except Exception as e:
                logger.error(f"Failed to load skill from {path}: {e}")
                validation.valid = False
                validation.errors.append(SkillValidationError(
                    field="load",
                    message=str(e)
                ))

    return count, _validation_results
