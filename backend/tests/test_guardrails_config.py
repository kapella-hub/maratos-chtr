"""Tests for guardrails configuration."""

import os
import pytest

from app.guardrails.config import (
    GuardrailsSettings,
    get_guardrails_settings,
    reset_guardrails_settings,
    get_budget_limits,
    get_diff_approval_config,
    get_audit_retention_config,
    get_agent_tool_allowlist,
    get_config_summary,
    validate_guardrails_config,
)


class TestGuardrailsSettings:
    """Test GuardrailsSettings pydantic model."""

    def test_default_values(self):
        """Test that defaults are safe and restrictive."""
        settings = GuardrailsSettings()

        # Budget defaults
        assert settings.max_tool_loops_per_message == 6
        assert settings.max_tool_calls_per_session == 100
        assert settings.max_spawned_tasks_per_run == 10
        assert settings.max_shell_time_seconds == 120.0

        # Diff-first defaults (disabled by default)
        assert settings.diff_first_enabled is False
        assert settings.diff_first_require_writes is True
        assert settings.diff_first_require_deletes is True

        # Audit defaults
        assert settings.audit_retention_days == 90
        assert settings.audit_compress_diffs is True
        assert settings.audit_hash_algorithm == "sha256"

        # Mode defaults (all off)
        assert settings.strict_mode is False
        assert settings.readonly_mode is False
        assert settings.sandbox_mode is False

    def test_validation_max_tool_loops(self):
        """Test validation of max_tool_loops_per_message."""
        # Valid value
        settings = GuardrailsSettings(max_tool_loops_per_message=10)
        assert settings.max_tool_loops_per_message == 10

        # Out of range
        with pytest.raises(ValueError):
            GuardrailsSettings(max_tool_loops_per_message=0)

        with pytest.raises(ValueError):
            GuardrailsSettings(max_tool_loops_per_message=25)

    def test_validation_hash_algorithm(self):
        """Test validation of hash algorithm."""
        # Valid values
        s1 = GuardrailsSettings(audit_hash_algorithm="sha256")
        assert s1.audit_hash_algorithm == "sha256"

        s2 = GuardrailsSettings(audit_hash_algorithm="SHA512")
        assert s2.audit_hash_algorithm == "sha512"  # Normalized to lowercase

        # Invalid value
        with pytest.raises(ValueError):
            GuardrailsSettings(audit_hash_algorithm="md5")

    def test_validation_protected_patterns(self):
        """Test validation of protected patterns."""
        # Valid patterns
        settings = GuardrailsSettings(
            diff_first_protected_patterns="*.py,*.js,*.ts"
        )
        assert "*.py" in settings.diff_first_protected_patterns

        # Empty pattern in list should fail
        with pytest.raises(ValueError):
            GuardrailsSettings(diff_first_protected_patterns="*.py,,*.js")


class TestBudgetLimits:
    """Test budget limits computation."""

    def setup_method(self):
        """Reset settings before each test."""
        reset_guardrails_settings()

    def teardown_method(self):
        """Clean up environment after each test."""
        reset_guardrails_settings()
        # Clear any env vars we set
        for key in list(os.environ.keys()):
            if key.startswith("MARATOS_GUARDRAILS_"):
                del os.environ[key]

    def test_normal_mode_limits(self):
        """Test limits in normal mode."""
        limits = get_budget_limits()

        assert limits.max_tool_loops_per_message == 6
        assert limits.max_tool_calls_per_session == 100
        assert limits.max_shell_time_seconds == 120.0

    def test_strict_mode_limits(self):
        """Test limits in strict mode."""
        os.environ["MARATOS_GUARDRAILS_STRICT_MODE"] = "true"
        reset_guardrails_settings()

        limits = get_budget_limits()

        # Strict mode should use minimum limits
        assert limits.max_tool_loops_per_message == 3
        assert limits.max_tool_calls_per_session == 50
        assert limits.max_shell_time_seconds == 30.0
        assert limits.max_output_size_bytes == 100_000


class TestDiffApprovalConfig:
    """Test diff approval configuration."""

    def setup_method(self):
        """Reset settings before each test."""
        reset_guardrails_settings()

    def teardown_method(self):
        """Clean up environment after each test."""
        reset_guardrails_settings()
        for key in list(os.environ.keys()):
            if key.startswith("MARATOS_GUARDRAILS_"):
                del os.environ[key]

    def test_disabled_by_default(self):
        """Test diff-first is disabled by default."""
        config = get_diff_approval_config()
        assert config.enabled is False

    def test_enabled_with_patterns(self):
        """Test enabled diff-first with custom patterns."""
        os.environ["MARATOS_GUARDRAILS_DIFF_FIRST_ENABLED"] = "true"
        os.environ["MARATOS_GUARDRAILS_DIFF_FIRST_PROTECTED_PATTERNS"] = "*.py,*.go"
        reset_guardrails_settings()

        config = get_diff_approval_config()

        assert config.enabled is True
        assert "*.py" in config.protected_patterns
        assert "*.go" in config.protected_patterns

    def test_readonly_mode_overrides(self):
        """Test readonly mode enables strict diff-first."""
        os.environ["MARATOS_GUARDRAILS_READONLY_MODE"] = "true"
        reset_guardrails_settings()

        config = get_diff_approval_config()

        assert config.enabled is True
        assert config.require_approval_for_writes is True
        assert config.require_approval_for_deletes is True
        assert config.require_approval_for_shell is True
        assert "*" in config.protected_patterns


class TestAuditRetentionConfig:
    """Test audit retention configuration."""

    def setup_method(self):
        """Reset settings before each test."""
        reset_guardrails_settings()

    def teardown_method(self):
        """Clean up environment after each test."""
        reset_guardrails_settings()
        for key in list(os.environ.keys()):
            if key.startswith("MARATOS_GUARDRAILS_"):
                del os.environ[key]

    def test_default_retention_days(self):
        """Test default retention days per table."""
        config = get_audit_retention_config()

        assert config.default_retention_days == 90
        assert config.policies["audit_logs"] == 90
        assert config.policies["tool_audit_logs"] == 60
        assert config.policies["llm_exchange_logs"] == 30
        assert config.policies["file_change_logs"] == 90
        assert config.policies["budget_logs"] == 30

    def test_compression_settings(self):
        """Test compression settings."""
        config = get_audit_retention_config()

        assert config.compress_diffs is True
        assert config.compression_threshold == 1000
        assert config.hash_algorithm == "sha256"
        assert config.preserve_hash_on_truncate is True

    def test_custom_retention(self):
        """Test custom retention settings."""
        os.environ["MARATOS_GUARDRAILS_AUDIT_RETENTION_DAYS"] = "365"
        os.environ["MARATOS_GUARDRAILS_AUDIT_LLM_RETENTION_DAYS"] = "90"
        reset_guardrails_settings()

        config = get_audit_retention_config()

        assert config.default_retention_days == 365
        assert config.policies["llm_exchange_logs"] == 90


class TestAgentToolAllowlist:
    """Test agent tool allowlist configuration."""

    def setup_method(self):
        """Reset settings before each test."""
        reset_guardrails_settings()

    def teardown_method(self):
        """Clean up environment after each test."""
        reset_guardrails_settings()
        for key in list(os.environ.keys()):
            if key.startswith("MARATOS_GUARDRAILS_"):
                del os.environ[key]

    def test_default_returns_none(self):
        """Test that empty config returns None (use defaults)."""
        tools = get_agent_tool_allowlist("coder")
        assert tools is None

    def test_custom_allowlist(self):
        """Test custom tool allowlist."""
        os.environ["MARATOS_GUARDRAILS_CODER_ALLOWED_TOOLS"] = "filesystem,kiro"
        reset_guardrails_settings()

        tools = get_agent_tool_allowlist("coder")

        assert tools is not None
        assert "filesystem" in tools
        assert "kiro" in tools
        assert "shell" not in tools

    def test_sandbox_mode_removes_shell(self):
        """Test sandbox mode removes shell from allowlist."""
        os.environ["MARATOS_GUARDRAILS_SANDBOX_MODE"] = "true"
        os.environ["MARATOS_GUARDRAILS_CODER_ALLOWED_TOOLS"] = "filesystem,shell,kiro"
        reset_guardrails_settings()

        tools = get_agent_tool_allowlist("coder")

        assert tools is not None
        assert "filesystem" in tools
        assert "kiro" in tools
        assert "shell" not in tools

    def test_readonly_mode_restricts_tools(self):
        """Test readonly mode restricts to read-only tools."""
        os.environ["MARATOS_GUARDRAILS_READONLY_MODE"] = "true"
        reset_guardrails_settings()

        tools = get_agent_tool_allowlist("coder")

        assert tools is not None
        assert "filesystem" in tools
        assert "web_search" in tools
        # Shell and write-capable tools should be removed
        assert "shell" not in tools


class TestConfigValidation:
    """Test configuration validation."""

    def setup_method(self):
        """Reset settings before each test."""
        reset_guardrails_settings()

    def teardown_method(self):
        """Clean up environment after each test."""
        reset_guardrails_settings()
        for key in list(os.environ.keys()):
            if key.startswith("MARATOS_GUARDRAILS_"):
                del os.environ[key]

    def test_valid_config_no_errors(self):
        """Test valid configuration produces no errors."""
        errors = validate_guardrails_config()
        assert errors == []

    def test_compression_threshold_fails_fast(self):
        """Test that compression threshold > max fails at validation time."""
        # When compression_threshold exceeds the max allowed (50000),
        # Pydantic validation rejects it immediately - this is "fail fast"
        os.environ["MARATOS_GUARDRAILS_AUDIT_COMPRESSION_THRESHOLD"] = "60000"
        reset_guardrails_settings()

        # Should fail with pydantic ValidationError (fail fast behavior)
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            get_guardrails_settings()

    def test_retention_days_consistency_warning(self):
        """Test warning when LLM retention > general retention."""
        # Set LLM retention higher than general retention (allowed but warned)
        os.environ["MARATOS_GUARDRAILS_AUDIT_RETENTION_DAYS"] = "30"
        os.environ["MARATOS_GUARDRAILS_AUDIT_LLM_RETENTION_DAYS"] = "90"
        reset_guardrails_settings()

        errors = validate_guardrails_config()

        assert len(errors) == 1
        assert "audit_llm_retention_days" in errors[0]


class TestConfigSummary:
    """Test configuration summary generation."""

    def setup_method(self):
        """Reset settings before each test."""
        reset_guardrails_settings()

    def teardown_method(self):
        """Clean up environment after each test."""
        reset_guardrails_settings()

    def test_summary_structure(self):
        """Test summary has expected structure."""
        summary = get_config_summary()

        assert "modes" in summary
        assert "budget_limits" in summary
        assert "audit_retention" in summary
        assert "validation_errors" in summary

        # Check modes
        assert "strict_mode" in summary["modes"]
        assert "readonly_mode" in summary["modes"]
        assert "sandbox_mode" in summary["modes"]
        assert "diff_first_enabled" in summary["modes"]

        # Check budget limits
        assert "max_tool_loops_per_message" in summary["budget_limits"]
        assert "max_shell_time_seconds" in summary["budget_limits"]

        # Check audit retention
        assert "default_days" in summary["audit_retention"]
        assert "compress_diffs" in summary["audit_retention"]
