"""Skills system for MaratOS - compatible with Kiro AI.

The skills system provides:
- Typed, composable build steps with validated I/O
- Deterministic skill selection based on task types
- Quality gates for verification
- Skill composition for complex workflows
"""

from app.skills.base import Skill, SkillStep, SkillRegistry, skill_registry
from app.skills.loader import load_skills_from_dir
from app.skills.schema import (
    SkillSchema,
    SkillStepSchema,
    InputField,
    OutputField,
    ArtifactSpec,
    QualityGate,
    RetryPolicy,
    TaskType,
    ArtifactType,
    ToolType,
    GateType,
    StepAction,
    validate_skill_yaml,
    parse_skill_file,
)
from app.skills.selector import (
    SkillSelector,
    SkillMatch,
    SkillSelection,
    skill_selector,
    get_skill_selector,
)

__all__ = [
    # Base
    "Skill",
    "SkillStep",
    "SkillRegistry",
    "skill_registry",
    "load_skills_from_dir",
    # Schema
    "SkillSchema",
    "SkillStepSchema",
    "InputField",
    "OutputField",
    "ArtifactSpec",
    "QualityGate",
    "RetryPolicy",
    "TaskType",
    "ArtifactType",
    "ToolType",
    "GateType",
    "StepAction",
    "validate_skill_yaml",
    "parse_skill_file",
    # Selector
    "SkillSelector",
    "SkillMatch",
    "SkillSelection",
    "skill_selector",
    "get_skill_selector",
]
