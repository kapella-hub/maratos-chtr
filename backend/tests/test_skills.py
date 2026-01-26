"""Tests for skill validation and loading."""

import tempfile
from pathlib import Path

import pytest

from app.skills.loader import (
    validate_skill_yaml,
    validate_all_skills,
    SkillValidationError,
    SkillValidationResult,
    REQUIRED_FIELDS,
    VALID_ACTIONS,
)


class TestSkillValidation:
    """Test skill YAML validation."""

    def test_valid_skill(self, tmp_path):
        """Test validation of a valid skill file."""
        skill_yaml = tmp_path / "valid.yaml"
        skill_yaml.write_text("""
id: test-skill
name: Test Skill
description: A test skill
version: "1.0.0"
triggers:
  - test
  - example
workflow:
  - name: step1
    action: kiro_prompt
    description: Test step
quality_checklist:
  - Check item 1
  - Check item 2
""")
        result = validate_skill_yaml(skill_yaml)
        assert result.valid is True
        assert result.skill_id == "test-skill"
        assert len(result.errors) == 0

    def test_missing_required_fields(self, tmp_path):
        """Test validation fails for missing required fields."""
        skill_yaml = tmp_path / "missing.yaml"
        skill_yaml.write_text("""
id: incomplete
# missing name and description
""")
        result = validate_skill_yaml(skill_yaml)
        assert result.valid is False
        assert len(result.errors) >= 2  # At least name and description missing
        error_fields = [e.field for e in result.errors]
        assert "name" in error_fields
        assert "description" in error_fields

    def test_invalid_yaml_syntax(self, tmp_path):
        """Test validation fails for invalid YAML."""
        skill_yaml = tmp_path / "invalid.yaml"
        skill_yaml.write_text("""
id: test
name: [invalid syntax
""")
        result = validate_skill_yaml(skill_yaml)
        assert result.valid is False
        assert any(e.field == "yaml" for e in result.errors)

    def test_no_triggers_warning(self, tmp_path):
        """Test warning when no triggers defined."""
        skill_yaml = tmp_path / "no_triggers.yaml"
        skill_yaml.write_text("""
id: no-triggers
name: No Triggers
description: Skill without triggers
workflow:
  - name: step1
    action: kiro_prompt
""")
        result = validate_skill_yaml(skill_yaml)
        assert result.valid is True
        assert len(result.warnings) > 0
        assert any(w.field == "triggers" for w in result.warnings)

    def test_invalid_workflow_action(self, tmp_path):
        """Test warning for unknown workflow action."""
        skill_yaml = tmp_path / "bad_action.yaml"
        skill_yaml.write_text("""
id: bad-action
name: Bad Action
description: Skill with unknown action
triggers:
  - test
workflow:
  - name: step1
    action: unknown_action
""")
        result = validate_skill_yaml(skill_yaml)
        # Should be valid but have warnings
        assert result.valid is True
        assert any("unknown_action" in w.message for w in result.warnings)

    def test_workflow_missing_name(self, tmp_path):
        """Test error for workflow step missing name."""
        skill_yaml = tmp_path / "missing_name.yaml"
        skill_yaml.write_text("""
id: missing-step-name
name: Missing Step Name
description: Test
triggers:
  - test
workflow:
  - action: kiro_prompt
    description: No name
""")
        result = validate_skill_yaml(skill_yaml)
        assert result.valid is False
        assert any("workflow" in e.field and "name" in e.message for e in result.errors)

    def test_workflow_missing_action(self, tmp_path):
        """Test error for workflow step missing action."""
        skill_yaml = tmp_path / "missing_action.yaml"
        skill_yaml.write_text("""
id: missing-step-action
name: Missing Step Action
description: Test
triggers:
  - test
workflow:
  - name: step1
    description: No action
""")
        result = validate_skill_yaml(skill_yaml)
        assert result.valid is False
        assert any("workflow" in e.field and "action" in e.message for e in result.errors)

    def test_not_a_dictionary(self, tmp_path):
        """Test error when YAML is not a dictionary."""
        skill_yaml = tmp_path / "not_dict.yaml"
        skill_yaml.write_text("""
- item1
- item2
""")
        result = validate_skill_yaml(skill_yaml)
        assert result.valid is False
        assert any(e.field == "root" for e in result.errors)

    def test_invalid_triggers_type(self, tmp_path):
        """Test error when triggers is not a list."""
        skill_yaml = tmp_path / "bad_triggers.yaml"
        skill_yaml.write_text("""
id: bad-triggers
name: Bad Triggers
description: Test
triggers: "not a list"
""")
        result = validate_skill_yaml(skill_yaml)
        assert result.valid is False
        assert any(e.field == "triggers" for e in result.errors)


class TestValidateAllSkills:
    """Test batch skill validation."""

    def test_validate_multiple_skills(self, tmp_path):
        """Test validating multiple skill files."""
        # Create valid skill
        (tmp_path / "valid.yaml").write_text("""
id: valid
name: Valid
description: Valid skill
triggers:
  - test
""")
        # Create invalid skill
        (tmp_path / "invalid.yaml").write_text("""
id: invalid
# missing name and description
""")

        results = validate_all_skills(tmp_path)
        assert len(results) == 2
        valid_count = sum(1 for r in results if r.valid)
        assert valid_count == 1

    def test_empty_directory(self, tmp_path):
        """Test validation of empty directory."""
        results = validate_all_skills(tmp_path)
        assert len(results) == 0

    def test_nonexistent_directory(self, tmp_path):
        """Test validation of non-existent directory."""
        results = validate_all_skills(tmp_path / "nonexistent")
        assert len(results) == 0


class TestValidActions:
    """Test that valid actions are properly defined."""

    def test_expected_actions_exist(self):
        """Test that expected actions are in VALID_ACTIONS."""
        expected = ["kiro_architect", "kiro_validate", "kiro_test", "kiro_prompt", "shell", "filesystem"]
        for action in expected:
            assert action in VALID_ACTIONS


class TestRequiredFields:
    """Test required fields constant."""

    def test_expected_required_fields(self):
        """Test that expected required fields are defined."""
        assert "id" in REQUIRED_FIELDS
        assert "name" in REQUIRED_FIELDS
        assert "description" in REQUIRED_FIELDS
