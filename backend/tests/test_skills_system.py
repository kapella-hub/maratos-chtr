"""Tests for the upgraded Skills system.

Tests:
- Schema validation
- Skill composition
- Selector mapping
"""

import pytest
from pathlib import Path


class TestSkillSchema:
    """Tests for skill schema validation."""

    def test_valid_skill_schema(self):
        """A valid skill schema should parse without errors."""
        from app.skills.schema import SkillSchema, TaskType, ToolType

        skill = SkillSchema(
            id="test-skill",
            name="Test Skill",
            description="A test skill",
            task_types=[TaskType.BOOTSTRAP_PROJECT],
            requires_tools=[ToolType.KIRO],
            workflow=[],
        )

        assert skill.id == "test-skill"
        assert skill.name == "Test Skill"

    def test_invalid_skill_id(self):
        """Skill ID must be lowercase with hyphens only."""
        from app.skills.schema import SkillSchema
        from pydantic import ValidationError

        with pytest.raises(ValidationError) as exc_info:
            SkillSchema(
                id="Invalid_ID",  # Invalid: uppercase and underscore
                name="Test",
                description="Test",
            )

        assert "id" in str(exc_info.value)

    def test_input_validation(self):
        """Skill inputs should be validated correctly."""
        from app.skills.schema import SkillSchema, InputField

        skill = SkillSchema(
            id="test-skill",
            name="Test",
            description="Test",
            inputs=[
                InputField(
                    name="project_name",
                    type="string",
                    required=True,
                ),
                InputField(
                    name="include_docker",
                    type="boolean",
                    required=False,
                    default=True,
                ),
            ],
        )

        # Valid inputs
        is_valid, errors = skill.validate_inputs({"project_name": "my-app"})
        assert is_valid
        assert len(errors) == 0

        # Missing required input
        is_valid, errors = skill.validate_inputs({})
        assert not is_valid
        assert "project_name" in errors[0]

    def test_quality_gate_schema(self):
        """Quality gates should validate correctly."""
        from app.skills.schema import QualityGate, GateType

        gate = QualityGate(
            id="tests_pass",
            type=GateType.TESTS_PASS,
            description="All tests must pass",
            required=True,
        )

        assert gate.type == GateType.TESTS_PASS
        assert gate.required is True

    def test_workflow_step_skill_reference(self):
        """Skill references in workflow must be declared in requires_skills."""
        from app.skills.schema import SkillSchema, SkillStepSchema, StepAction
        from pydantic import ValidationError

        # This should fail - skill referenced but not in requires_skills
        with pytest.raises(ValidationError) as exc_info:
            SkillSchema(
                id="test-skill",
                name="Test",
                description="Test",
                requires_skills=[],  # Empty!
                workflow=[
                    SkillStepSchema(
                        name="call_other",
                        action=StepAction.SKILL,
                        skill_id="other-skill",  # Not in requires_skills
                    )
                ],
            )

        assert "requires_skills" in str(exc_info.value)

    def test_json_schema_generation(self):
        """Skill should generate valid JSON schema for inputs."""
        from app.skills.schema import SkillSchema, InputField

        skill = SkillSchema(
            id="test-skill",
            name="Test",
            description="Test",
            inputs=[
                InputField(
                    name="project_name",
                    type="string",
                    required=True,
                    description="Name of the project",
                ),
                InputField(
                    name="port",
                    type="number",
                    required=False,
                    default=8000,
                ),
            ],
        )

        schema = skill.to_json_schema()

        assert schema["type"] == "object"
        assert "project_name" in schema["properties"]
        assert "port" in schema["properties"]
        assert "project_name" in schema["required"]
        assert "port" not in schema["required"]

    def test_artifact_spec(self):
        """Artifact specifications should be valid."""
        from app.skills.schema import ArtifactSpec, ArtifactType

        artifact = ArtifactSpec(
            name="dockerfile",
            type=ArtifactType.DOCKER,
            path_template="{{workdir}}/Dockerfile",
            description="Docker configuration file",
        )

        assert artifact.type == ArtifactType.DOCKER
        assert "{{workdir}}" in artifact.path_template

    def test_retry_policy(self):
        """Retry policy should have sensible defaults."""
        from app.skills.schema import RetryPolicy

        policy = RetryPolicy()

        assert policy.max_attempts == 3
        assert policy.backoff_seconds == 2.0
        assert policy.backoff_multiplier == 2.0


class TestSkillSelector:
    """Tests for skill selection and mapping."""

    def test_detect_task_type_bootstrap(self):
        """Should detect bootstrap project task type."""
        from app.skills.selector import SkillSelector
        from app.skills.schema import TaskType

        selector = SkillSelector()

        # Various bootstrap phrasings
        assert selector.detect_task_type("create a new fastapi project") == TaskType.BOOTSTRAP_PROJECT
        assert selector.detect_task_type("bootstrap a new react app") == TaskType.BOOTSTRAP_PROJECT
        assert selector.detect_task_type("new django project") == TaskType.BOOTSTRAP_PROJECT
        assert selector.detect_task_type("build me a fastapi app") == TaskType.BOOTSTRAP_PROJECT

    def test_detect_task_type_docker(self):
        """Should detect dockerize task type."""
        from app.skills.selector import SkillSelector
        from app.skills.schema import TaskType

        selector = SkillSelector()

        assert selector.detect_task_type("add docker to this project") == TaskType.DOCKERIZE
        assert selector.detect_task_type("dockerize the app") == TaskType.DOCKERIZE
        assert selector.detect_task_type("create docker compose") == TaskType.DOCKERIZE

    def test_detect_task_type_ci(self):
        """Should detect CI/CD task type."""
        from app.skills.selector import SkillSelector
        from app.skills.schema import TaskType

        selector = SkillSelector()

        assert selector.detect_task_type("add CI pipeline") == TaskType.ADD_CI
        assert selector.detect_task_type("setup github actions") == TaskType.ADD_CI
        assert selector.detect_task_type("add continuous integration") == TaskType.ADD_CI

    def test_detect_framework_fastapi(self):
        """Should detect FastAPI framework."""
        from app.skills.selector import SkillSelector

        selector = SkillSelector()

        assert selector.detect_framework("create a FastAPI project") == "fastapi"
        assert selector.detect_framework("build a fast api backend") == "fastapi"

    def test_detect_framework_react(self):
        """Should detect React framework."""
        from app.skills.selector import SkillSelector

        selector = SkillSelector()

        assert selector.detect_framework("create a React app") == "react"
        assert selector.detect_framework("build a Next.js frontend") == "react"

    def test_select_skill_for_fastapi_bootstrap(self):
        """Should select correct skill for FastAPI bootstrap."""
        from app.skills.selector import SkillSelector

        selector = SkillSelector()
        selection = selector.select("create a new FastAPI project")

        assert selection.primary_skill is not None
        assert selection.primary_skill.skill_id == "project-bootstrap-fastapi"
        assert selection.primary_skill.confidence >= 0.5

    def test_select_skill_for_react_bootstrap(self):
        """Should select correct skill for React bootstrap."""
        from app.skills.selector import SkillSelector

        selector = SkillSelector()
        selection = selector.select("bootstrap a new React application")

        assert selection.primary_skill is not None
        assert selection.primary_skill.skill_id == "project-bootstrap-react"

    def test_detect_composition(self):
        """Should detect when multiple skills are needed."""
        from app.skills.selector import SkillSelector

        selector = SkillSelector()
        selection = selector.select(
            "create a FastAPI project with docker and CI"
        )

        # Should include composition
        assert len(selection.composition) >= 2
        assert "dockerize-and-compose" in selection.composition
        assert "add-ci-pipeline" in selection.composition

    def test_ambiguous_request_needs_planning(self):
        """Ambiguous requests should require Architect planning."""
        from app.skills.selector import SkillSelector

        selector = SkillSelector()
        selection = selector.select("improve the system")

        # No clear task type - needs planning
        assert selection.requires_planning is True

    def test_get_skill_for_task(self):
        """Simple skill lookup should work."""
        from app.skills.selector import SkillSelector

        selector = SkillSelector()

        skill_id = selector.get_skill_for_task("add docker to this project")
        assert skill_id == "dockerize-and-compose"

        skill_id = selector.get_skill_for_task("run security review")
        assert skill_id == "security-review"

    def test_get_composition_for_request(self):
        """Should return ordered skill list for complex request."""
        from app.skills.selector import SkillSelector

        selector = SkillSelector()

        skills = selector.get_composition_for_request(
            "create a FastAPI app with docker, CI, and run security review"
        )

        assert len(skills) >= 3
        # Docker and CI should be included
        assert any("docker" in s for s in skills)
        assert any("ci" in s for s in skills)
        assert any("security" in s for s in skills)


class TestSkillComposition:
    """Tests for skill composition."""

    def test_skill_can_reference_other_skills(self):
        """Skills should be able to call other skills."""
        from app.skills.schema import (
            SkillSchema,
            SkillStepSchema,
            StepAction,
        )

        skill = SkillSchema(
            id="meta-skill",
            name="Meta Skill",
            description="Calls other skills",
            requires_skills=["sub-skill-1", "sub-skill-2"],
            workflow=[
                SkillStepSchema(
                    name="call_sub_1",
                    action=StepAction.SKILL,
                    skill_id="sub-skill-1",
                    skill_inputs={"param": "value"},
                ),
                SkillStepSchema(
                    name="call_sub_2",
                    action=StepAction.SKILL,
                    skill_id="sub-skill-2",
                ),
            ],
        )

        assert len(skill.workflow) == 2
        assert skill.workflow[0].skill_id == "sub-skill-1"
        assert skill.workflow[0].skill_inputs == {"param": "value"}

    def test_parallel_steps(self):
        """Skills should support parallel step execution."""
        from app.skills.schema import (
            SkillSchema,
            SkillStepSchema,
            StepAction,
        )

        skill = SkillSchema(
            id="parallel-skill",
            name="Parallel Skill",
            description="Runs steps in parallel",
            workflow=[
                SkillStepSchema(
                    name="parallel_group",
                    action=StepAction.PARALLEL,
                    parallel_steps=[
                        SkillStepSchema(
                            name="step_a",
                            action=StepAction.SHELL,
                            params={"command": "echo a"},
                        ),
                        SkillStepSchema(
                            name="step_b",
                            action=StepAction.SHELL,
                            params={"command": "echo b"},
                        ),
                    ],
                ),
            ],
        )

        assert skill.workflow[0].action == StepAction.PARALLEL
        assert len(skill.workflow[0].parallel_steps) == 2

    def test_conditional_branching(self):
        """Skills should support conditional branching."""
        from app.skills.schema import (
            SkillSchema,
            SkillStepSchema,
            StepAction,
        )

        skill = SkillSchema(
            id="conditional-skill",
            name="Conditional Skill",
            description="Has conditional branches",
            workflow=[
                SkillStepSchema(
                    name="conditional_step",
                    action=StepAction.CONDITIONAL,
                    condition="project_type == python",
                    branches={
                        "python": [
                            SkillStepSchema(
                                name="python_setup",
                                action=StepAction.SHELL,
                                params={"command": "pip install"},
                            ),
                        ],
                        "node": [
                            SkillStepSchema(
                                name="node_setup",
                                action=StepAction.SHELL,
                                params={"command": "npm install"},
                            ),
                        ],
                    },
                ),
            ],
        )

        assert skill.workflow[0].action == StepAction.CONDITIONAL
        assert "python" in skill.workflow[0].branches
        assert "node" in skill.workflow[0].branches


class TestMacroSkillLoading:
    """Tests for loading macro skills."""

    def test_load_fastapi_bootstrap_skill(self):
        """FastAPI bootstrap skill should load and validate."""
        from app.skills.schema import parse_skill_file
        from pathlib import Path

        skill_path = Path(__file__).parent.parent / "skills" / "macro" / "project-bootstrap-fastapi.yaml"
        if not skill_path.exists():
            pytest.skip("Macro skills not found")

        skill, errors = parse_skill_file(str(skill_path))

        if errors:
            pytest.fail(f"Skill validation errors: {errors}")

        assert skill is not None
        assert skill.id == "project-bootstrap-fastapi"
        assert len(skill.inputs) >= 2
        assert len(skill.workflow) >= 3

    def test_load_app_factory_skill(self):
        """App Factory meta-skill should load and validate."""
        from app.skills.schema import parse_skill_file
        from pathlib import Path

        skill_path = Path(__file__).parent.parent / "skills" / "macro" / "app-factory.yaml"
        if not skill_path.exists():
            pytest.skip("Macro skills not found")

        skill, errors = parse_skill_file(str(skill_path))

        if errors:
            pytest.fail(f"Skill validation errors: {errors}")

        assert skill is not None
        assert skill.id == "app-factory"
        # v2.0 uses deterministic templates instead of composing skills
        assert len(skill.quality_gates) >= 3
        # Verify it has the template_generate action
        has_template_generate = any(
            step.action.value == "template_generate"
            for step in skill.workflow
        )
        assert has_template_generate, "app-factory should use template_generate action"


class TestIntegration:
    """Integration tests for the skills system."""

    def test_full_workflow_selection(self):
        """Full workflow from prompt to skill selection."""
        from app.skills.selector import get_skill_selector

        selector = get_skill_selector()

        # User wants a full-stack app
        prompt = "Build me a FastAPI + React skeleton with docker compose and CI"
        selection = selector.select(prompt)

        # Should identify bootstrap as primary
        assert selection.primary_skill is not None
        assert "fastapi" in selection.primary_skill.skill_id

        # Should compose with docker and CI
        assert "dockerize-and-compose" in selection.composition
        assert "add-ci-pipeline" in selection.composition

    def test_selector_custom_mapping(self):
        """Custom mappings should override defaults."""
        from app.skills.selector import SkillSelector
        from app.skills.schema import TaskType

        selector = SkillSelector()

        # Add custom mapping
        selector.add_mapping(TaskType.BOOTSTRAP_PROJECT, "my-custom-bootstrap")

        selection = selector.select("create a new project")

        assert selection.primary_skill.skill_id == "my-custom-bootstrap"
