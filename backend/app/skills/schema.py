"""Extended skill schema with typed inputs/outputs and composition support.

This module provides Pydantic models for validating skill definitions,
ensuring deterministic execution without LLM guessing.
"""

from enum import Enum
from typing import Any, Literal
from pydantic import BaseModel, Field, field_validator, model_validator
import json


# =============================================================================
# Enums
# =============================================================================


class ArtifactType(str, Enum):
    """Types of artifacts a skill can produce."""
    FILE = "file"
    DIRECTORY = "directory"
    CONFIG = "config"
    CODE = "code"
    TEST = "test"
    DOCUMENTATION = "documentation"
    REPORT = "report"
    DOCKER = "docker"
    CI_CONFIG = "ci_config"
    DATABASE = "database"
    JSON = "json"
    MARKDOWN = "markdown"


class ToolType(str, Enum):
    """Tool types that skills can require."""
    KIRO = "kiro"
    SHELL = "shell"
    FILESYSTEM = "filesystem"
    GIT = "git"
    DOCKER = "docker"
    NPM = "npm"
    PIP = "pip"
    PYTEST = "pytest"


class GateType(str, Enum):
    """Quality gate verification types."""
    TESTS_PASS = "tests_pass"
    LINT_CLEAN = "lint_clean"
    TYPE_CHECK = "type_check"
    BUILD_SUCCESS = "build_success"
    SECURITY_SCAN = "security_scan"
    COVERAGE_THRESHOLD = "coverage_threshold"
    FILE_EXISTS = "file_exists"
    COMMAND_SUCCESS = "command_success"
    SKILL_OUTPUT = "skill_output"


class StepAction(str, Enum):
    """Valid step actions."""
    KIRO_ARCHITECT = "kiro_architect"
    KIRO_VALIDATE = "kiro_validate"
    KIRO_TEST = "kiro_test"
    KIRO_PROMPT = "kiro_prompt"
    SHELL = "shell"
    FILESYSTEM = "filesystem"
    SKILL = "skill"  # Call another skill (composition)
    PARALLEL = "parallel"  # Run multiple steps in parallel
    CONDITIONAL = "conditional"  # Branching logic
    TEMPLATE_GENERATE = "template_generate"  # Deterministic template generation


class TaskType(str, Enum):
    """Task types for skill selector mapping."""
    BOOTSTRAP_PROJECT = "bootstrap_project"
    ADD_FEATURE = "add_feature"
    ADD_API_ENDPOINT = "add_api_endpoint"
    ADD_UI_COMPONENT = "add_ui_component"
    DOCKERIZE = "dockerize"
    ADD_CI = "add_ci"
    ADD_DATABASE = "add_database"
    ADD_AUTH = "add_auth"
    SECURITY_REVIEW = "security_review"
    DOCUMENTATION = "documentation"
    REFACTOR = "refactor"
    TEST = "test"
    BUILD = "build"
    DEPLOY = "deploy"


# =============================================================================
# Input/Output Schemas
# =============================================================================


class InputField(BaseModel):
    """Schema for a skill input field."""
    name: str
    type: Literal["string", "number", "boolean", "array", "object", "path", "file_pattern", "list", "enum"] = "string"
    description: str = ""
    required: bool = True
    default: Any = None
    validation: str | None = None  # Regex or JSONSchema for validation
    enum_values: list[str] | None = None  # Valid values for enum type
    examples: list[Any] = Field(default_factory=list)


class OutputField(BaseModel):
    """Schema for a skill output field."""
    name: str
    type: Literal["string", "number", "boolean", "array", "object", "path", "artifact"] = "string"
    description: str = ""
    artifact_type: ArtifactType | None = None


class ArtifactSpec(BaseModel):
    """Specification for an artifact a skill produces."""
    name: str
    type: ArtifactType
    path_template: str  # e.g., "{{workdir}}/Dockerfile"
    description: str = ""
    required: bool = True


# =============================================================================
# Quality Gates
# =============================================================================


class QualityGate(BaseModel):
    """A quality gate that must pass for the skill to succeed."""
    id: str
    type: GateType
    description: str = ""
    command: str | None = None  # For COMMAND_SUCCESS
    threshold: float | None = None  # For COVERAGE_THRESHOLD
    file_path: str | None = None  # For FILE_EXISTS
    required: bool = True
    timeout_seconds: int = 300


class RetryPolicy(BaseModel):
    """Retry policy for skill execution."""
    max_attempts: int = 3
    backoff_seconds: float = 2.0
    backoff_multiplier: float = 2.0
    retry_on_errors: list[str] = Field(default_factory=lambda: ["timeout", "transient"])


# =============================================================================
# Workflow Steps
# =============================================================================


class SkillStepSchema(BaseModel):
    """Schema for a workflow step."""
    name: str
    action: StepAction
    description: str = ""
    params: dict[str, Any] = Field(default_factory=dict)
    condition: str | None = None

    # For skill composition
    skill_id: str | None = None  # When action=skill
    skill_inputs: dict[str, Any] = Field(default_factory=dict)

    # For parallel execution
    parallel_steps: list["SkillStepSchema"] = Field(default_factory=list)

    # For conditional branching
    branches: dict[str, list["SkillStepSchema"]] = Field(default_factory=dict)

    # Retry at step level
    retry: RetryPolicy | None = None
    timeout_seconds: int = 600

    @field_validator("skill_id")
    @classmethod
    def validate_skill_id(cls, v, info):
        """Ensure skill_id is set when action is skill."""
        if info.data.get("action") == StepAction.SKILL and not v:
            raise ValueError("skill_id required when action is 'skill'")
        return v


# =============================================================================
# Main Skill Schema
# =============================================================================


class SkillSchema(BaseModel):
    """Complete typed skill schema with validation."""

    # Identity
    id: str = Field(..., pattern=r"^[a-z][a-z0-9-]*$")
    name: str
    description: str
    version: str = "1.0.0"

    # Categorization
    task_types: list[TaskType] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    triggers: list[str] = Field(default_factory=list)

    # Typed I/O
    inputs: list[InputField] = Field(default_factory=list)
    outputs: list[OutputField] = Field(default_factory=list)

    # Artifacts
    produces: list[ArtifactSpec] = Field(default_factory=list)

    # Requirements
    requires_tools: list[ToolType] = Field(default_factory=list)
    requires_skills: list[str] = Field(default_factory=list)  # Skill dependencies

    # Quality
    quality_gates: list[QualityGate] = Field(default_factory=list)
    quality_checklist: list[str] = Field(default_factory=list)
    test_requirements: list[str] = Field(default_factory=list)

    # Execution
    workflow: list[SkillStepSchema] = Field(default_factory=list)
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)
    timeout_seconds: int = 3600  # Overall skill timeout

    # Context
    system_context: str = ""

    # Metadata
    author: str = ""

    @model_validator(mode="after")
    def validate_skill_references(self):
        """Validate that skill references in workflow are listed in requires_skills."""
        skill_refs = set()
        for step in self.workflow:
            if step.action == StepAction.SKILL and step.skill_id:
                skill_refs.add(step.skill_id)

        missing = skill_refs - set(self.requires_skills)
        if missing:
            raise ValueError(f"Skills referenced in workflow but not in requires_skills: {missing}")

        return self

    def get_required_inputs(self) -> list[InputField]:
        """Get all required inputs."""
        return [i for i in self.inputs if i.required]

    def validate_inputs(self, provided: dict[str, Any]) -> tuple[bool, list[str]]:
        """Validate provided inputs against schema.

        Returns (is_valid, list_of_errors).
        """
        errors = []

        for input_field in self.inputs:
            if input_field.required and input_field.name not in provided:
                if input_field.default is None:
                    errors.append(f"Missing required input: {input_field.name}")

        for key in provided:
            matching = [i for i in self.inputs if i.name == key]
            if not matching:
                errors.append(f"Unknown input: {key}")

        return len(errors) == 0, errors

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return self.model_dump()

    def to_json_schema(self) -> dict[str, Any]:
        """Generate JSON Schema for inputs."""
        properties = {}
        required = []

        for input_field in self.inputs:
            prop = {"description": input_field.description}

            type_map = {
                "string": "string",
                "number": "number",
                "boolean": "boolean",
                "array": "array",
                "object": "object",
                "path": "string",
                "file_pattern": "string",
            }
            prop["type"] = type_map.get(input_field.type, "string")

            if input_field.default is not None:
                prop["default"] = input_field.default
            if input_field.examples:
                prop["examples"] = input_field.examples

            properties[input_field.name] = prop

            if input_field.required:
                required.append(input_field.name)

        return {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": properties,
            "required": required,
        }


# =============================================================================
# Validation Utilities
# =============================================================================


def validate_skill_yaml(data: dict[str, Any]) -> tuple[bool, list[str], SkillSchema | None]:
    """Validate a skill YAML dictionary against the schema.

    Returns (is_valid, errors, parsed_skill).
    """
    try:
        skill = SkillSchema(**data)
        return True, [], skill
    except Exception as e:
        return False, [str(e)], None


def parse_skill_file(path: str) -> tuple[SkillSchema | None, list[str]]:
    """Parse a skill file (YAML or JSON) and validate.

    Returns (skill, errors).
    """
    import yaml
    from pathlib import Path

    file_path = Path(path)
    errors = []

    try:
        with open(file_path) as f:
            if file_path.suffix in (".yaml", ".yml"):
                data = yaml.safe_load(f)
            else:
                data = json.load(f)

        is_valid, parse_errors, skill = validate_skill_yaml(data)

        if not is_valid:
            return None, parse_errors

        return skill, []

    except Exception as e:
        return None, [f"Failed to parse {path}: {e}"]


# =============================================================================
# Example Skill (for documentation)
# =============================================================================

EXAMPLE_SKILL = {
    "id": "project-bootstrap-fastapi",
    "name": "Bootstrap FastAPI Project",
    "description": "Creates a new FastAPI project with standard structure",
    "version": "1.0.0",
    "task_types": ["bootstrap_project"],
    "tags": ["python", "fastapi", "api", "backend"],
    "triggers": ["create fastapi", "new api project", "bootstrap api"],

    "inputs": [
        {
            "name": "project_name",
            "type": "string",
            "description": "Name of the project",
            "required": True,
            "validation": "^[a-z][a-z0-9_-]*$",
        },
        {
            "name": "workdir",
            "type": "path",
            "description": "Directory to create project in",
            "required": True,
        },
        {
            "name": "include_docker",
            "type": "boolean",
            "description": "Include Dockerfile",
            "default": True,
        },
    ],

    "outputs": [
        {
            "name": "project_path",
            "type": "path",
            "description": "Path to created project",
        },
        {
            "name": "created_files",
            "type": "array",
            "description": "List of files created",
        },
    ],

    "produces": [
        {
            "name": "main_app",
            "type": "code",
            "path_template": "{{workdir}}/{{project_name}}/app/main.py",
            "description": "Main FastAPI application",
        },
        {
            "name": "dockerfile",
            "type": "docker",
            "path_template": "{{workdir}}/{{project_name}}/Dockerfile",
            "required": False,
        },
    ],

    "requires_tools": ["kiro", "shell", "filesystem"],

    "quality_gates": [
        {
            "id": "structure_valid",
            "type": "file_exists",
            "file_path": "{{workdir}}/{{project_name}}/app/main.py",
        },
        {
            "id": "lint_passes",
            "type": "command_success",
            "command": "cd {{workdir}}/{{project_name}} && ruff check .",
        },
    ],

    "workflow": [
        {
            "name": "create_structure",
            "action": "kiro_architect",
            "description": "Design and create project structure",
            "params": {
                "task": "Create FastAPI project '{{project_name}}' with app/, tests/, and config",
                "workdir": "{{workdir}}",
            },
        },
        {
            "name": "add_dockerfile",
            "action": "filesystem",
            "condition": "include_docker == true",
            "params": {
                "action": "write",
                "path": "{{workdir}}/{{project_name}}/Dockerfile",
                "content": "FROM python:3.11-slim\n...",
            },
        },
    ],

    "retry_policy": {
        "max_attempts": 2,
        "backoff_seconds": 5.0,
    },
}
