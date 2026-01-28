"""Unified guardrails configuration for enterprise deployments.

Single configuration surface for:
- Budget limits (tool loops, shell time, spawn limits)
- Tool allowlists per agent
- Diff-first required actions
- Audit retention (days), max payload sizes, hashing policy

All settings have safe, restrictive defaults. Missing config = safe mode.
"""

import logging
from dataclasses import dataclass
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


# =============================================================================
# Pydantic Settings for Environment Variables
# =============================================================================


class GuardrailsSettings(BaseSettings):
    """Guardrails configuration from environment variables.

    All settings use MARATOS_GUARDRAILS_ prefix.
    Defaults are safe and restrictive - missing config = secure mode.
    """

    model_config = SettingsConfigDict(
        env_prefix="MARATOS_GUARDRAILS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # =========================================================================
    # Budget Limits - Prevent runaway agent loops
    # =========================================================================

    # Tool loop limits
    max_tool_loops_per_message: int = Field(
        default=6,
        ge=1,
        le=20,
        description="Max tool loop iterations per message (1-20)",
    )
    max_tool_calls_per_message: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Max total tool calls per message (1-100)",
    )
    max_tool_calls_per_session: int = Field(
        default=100,
        ge=1,
        le=1000,
        description="Max tool calls per session (1-1000)",
    )

    # Spawn limits
    max_spawned_tasks_per_run: int = Field(
        default=10,
        ge=0,
        le=50,
        description="Max subagent spawns per orchestrator run (0-50)",
    )
    max_nested_spawn_depth: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Max depth of nested agent spawns (1-10)",
    )

    # Shell execution limits
    max_shell_time_seconds: float = Field(
        default=120.0,
        ge=1.0,
        le=600.0,
        description="Max time per shell command in seconds (1-600)",
    )
    max_shell_calls_per_message: int = Field(
        default=10,
        ge=0,
        le=50,
        description="Max shell invocations per message (0-50)",
    )
    max_total_shell_time_per_session: float = Field(
        default=600.0,
        ge=60.0,
        le=3600.0,
        description="Max total shell time per session in seconds (60-3600)",
    )

    # Output limits
    max_output_size_bytes: int = Field(
        default=1_000_000,
        ge=10_000,
        le=10_000_000,
        description="Max output per tool call in bytes (10KB-10MB)",
    )

    # =========================================================================
    # Diff-First Mode - Require approval for high-impact actions
    # =========================================================================

    diff_first_enabled: bool = Field(
        default=False,
        description="Enable diff-first mode globally (show diffs before execution)",
    )
    diff_first_require_writes: bool = Field(
        default=True,
        description="Require approval for file writes when diff-first is enabled",
    )
    diff_first_require_deletes: bool = Field(
        default=True,
        description="Require approval for file deletes when diff-first is enabled",
    )
    diff_first_require_shell: bool = Field(
        default=False,
        description="Require approval for shell commands when diff-first is enabled",
    )
    diff_first_timeout_seconds: float = Field(
        default=300.0,
        ge=30.0,
        le=3600.0,
        description="Timeout for diff approval in seconds (30-3600)",
    )
    diff_first_protected_patterns: str = Field(
        default="*.py,*.js,*.ts,*.yaml,*.yml,*.json,Dockerfile*,*.sql",
        description="Comma-separated patterns for protected files requiring approval",
    )

    # =========================================================================
    # Audit Retention - Control log storage and cleanup
    # =========================================================================

    audit_retention_days: int = Field(
        default=90,
        ge=1,
        le=365,
        description="Days to keep audit logs (1-365)",
    )
    audit_tool_retention_days: int = Field(
        default=60,
        ge=1,
        le=365,
        description="Days to keep tool audit logs (1-365)",
    )
    audit_llm_retention_days: int = Field(
        default=30,
        ge=1,
        le=365,
        description="Days to keep LLM exchange logs (1-365)",
    )
    audit_file_retention_days: int = Field(
        default=90,
        ge=1,
        le=365,
        description="Days to keep file change logs (1-365)",
    )
    audit_budget_retention_days: int = Field(
        default=30,
        ge=1,
        le=365,
        description="Days to keep budget logs (1-365)",
    )

    # Size limits for audit payloads
    audit_max_diff_size: int = Field(
        default=50_000,
        ge=1_000,
        le=1_000_000,
        description="Max diff size in bytes before truncation (1KB-1MB)",
    )
    audit_max_error_size: int = Field(
        default=10_000,
        ge=500,
        le=100_000,
        description="Max error message size in bytes (500B-100KB)",
    )
    audit_max_content_size: int = Field(
        default=5_000,
        ge=500,
        le=100_000,
        description="Max redacted content size in bytes (500B-100KB)",
    )
    audit_max_params_size: int = Field(
        default=10_000,
        ge=500,
        le=100_000,
        description="Max params JSON size in bytes (500B-100KB)",
    )

    # Compression settings
    audit_compress_diffs: bool = Field(
        default=True,
        description="Enable gzip compression for large diffs",
    )
    audit_compression_threshold: int = Field(
        default=1_000,
        ge=100,
        le=50_000,
        description="Compress diffs larger than this (bytes)",
    )

    # Hashing policy
    audit_hash_algorithm: str = Field(
        default="sha256",
        description="Hash algorithm for content verification (sha256, sha512)",
    )
    audit_preserve_hash_on_truncate: bool = Field(
        default=True,
        description="Always preserve original hash when truncating content",
    )

    # =========================================================================
    # Agent Tool Allowlists - Restrict tool access per agent
    # =========================================================================

    # Tool allowlists per agent (comma-separated)
    # Empty = use default from AGENT_POLICIES
    mo_allowed_tools: str = Field(
        default="",
        description="Allowed tools for MO agent (comma-separated, empty=default)",
    )
    architect_allowed_tools: str = Field(
        default="",
        description="Allowed tools for Architect agent (comma-separated, empty=default)",
    )
    coder_allowed_tools: str = Field(
        default="",
        description="Allowed tools for Coder agent (comma-separated, empty=default)",
    )
    reviewer_allowed_tools: str = Field(
        default="",
        description="Allowed tools for Reviewer agent (comma-separated, empty=default)",
    )
    tester_allowed_tools: str = Field(
        default="",
        description="Allowed tools for Tester agent (comma-separated, empty=default)",
    )
    docs_allowed_tools: str = Field(
        default="",
        description="Allowed tools for Docs agent (comma-separated, empty=default)",
    )
    devops_allowed_tools: str = Field(
        default="",
        description="Allowed tools for DevOps agent (comma-separated, empty=default)",
    )

    # =========================================================================
    # Enterprise Mode Flags
    # =========================================================================

    strict_mode: bool = Field(
        default=False,
        description="Enable strict mode: all limits at minimum, no shell, workspace-only",
    )
    readonly_mode: bool = Field(
        default=False,
        description="Enable readonly mode: no writes or deletes allowed",
    )
    sandbox_mode: bool = Field(
        default=False,
        description="Enable sandbox mode: workspace-only writes for all agents",
    )

    # =========================================================================
    # Validators
    # =========================================================================

    @field_validator("audit_hash_algorithm")
    @classmethod
    def validate_hash_algorithm(cls, v: str) -> str:
        """Validate hash algorithm."""
        valid = ["sha256", "sha512"]
        if v.lower() not in valid:
            raise ValueError(f"audit_hash_algorithm must be one of: {', '.join(valid)}")
        return v.lower()

    @field_validator("diff_first_protected_patterns")
    @classmethod
    def validate_protected_patterns(cls, v: str) -> str:
        """Validate protected patterns format."""
        if v:
            patterns = [p.strip() for p in v.split(",")]
            for pattern in patterns:
                if not pattern:
                    raise ValueError("Empty pattern in diff_first_protected_patterns")
        return v


# =============================================================================
# Configuration Instance Management
# =============================================================================

_settings: GuardrailsSettings | None = None


def get_guardrails_settings() -> GuardrailsSettings:
    """Get the global guardrails settings instance.

    Creates instance on first access. Thread-safe via Python's GIL.
    """
    global _settings
    if _settings is None:
        _settings = GuardrailsSettings()
        logger.info("Guardrails configuration loaded")
        _log_active_settings(_settings)
    return _settings


def reset_guardrails_settings() -> None:
    """Reset settings to reload from environment. Used for testing."""
    global _settings
    _settings = None


def _log_active_settings(settings: GuardrailsSettings) -> None:
    """Log active guardrails settings for debugging."""
    if settings.strict_mode:
        logger.warning("STRICT MODE ENABLED: All limits at minimum")
    if settings.readonly_mode:
        logger.warning("READONLY MODE ENABLED: No writes or deletes allowed")
    if settings.sandbox_mode:
        logger.warning("SANDBOX MODE ENABLED: Workspace-only writes for all agents")
    if settings.diff_first_enabled:
        logger.info("Diff-first mode enabled")


# =============================================================================
# Derived Configuration Helpers
# =============================================================================


@dataclass
class BudgetLimits:
    """Computed budget limits from settings."""

    max_tool_loops_per_message: int
    max_tool_calls_per_message: int
    max_tool_calls_per_session: int
    max_spawned_tasks_per_run: int
    max_nested_spawn_depth: int
    max_shell_time_seconds: float
    max_shell_calls_per_message: int
    max_total_shell_time_per_session: float
    max_output_size_bytes: int


@dataclass
class DiffApprovalConfig:
    """Computed diff-approval configuration from settings."""

    enabled: bool
    require_approval_for_writes: bool
    require_approval_for_deletes: bool
    require_approval_for_shell: bool
    approval_timeout_seconds: float
    protected_patterns: list[str]


@dataclass
class AuditRetentionConfig:
    """Computed audit retention configuration from settings."""

    default_retention_days: int
    policies: dict[str, int]  # table_name -> retention_days
    max_diff_size: int
    max_error_size: int
    max_content_size: int
    max_params_size: int
    compress_diffs: bool
    compression_threshold: int
    hash_algorithm: str
    preserve_hash_on_truncate: bool


def get_budget_limits() -> BudgetLimits:
    """Get computed budget limits from settings."""
    settings = get_guardrails_settings()

    # In strict mode, use minimum limits
    if settings.strict_mode:
        return BudgetLimits(
            max_tool_loops_per_message=3,
            max_tool_calls_per_message=10,
            max_tool_calls_per_session=50,
            max_spawned_tasks_per_run=3,
            max_nested_spawn_depth=2,
            max_shell_time_seconds=30.0,
            max_shell_calls_per_message=3,
            max_total_shell_time_per_session=120.0,
            max_output_size_bytes=100_000,
        )

    return BudgetLimits(
        max_tool_loops_per_message=settings.max_tool_loops_per_message,
        max_tool_calls_per_message=settings.max_tool_calls_per_message,
        max_tool_calls_per_session=settings.max_tool_calls_per_session,
        max_spawned_tasks_per_run=settings.max_spawned_tasks_per_run,
        max_nested_spawn_depth=settings.max_nested_spawn_depth,
        max_shell_time_seconds=settings.max_shell_time_seconds,
        max_shell_calls_per_message=settings.max_shell_calls_per_message,
        max_total_shell_time_per_session=settings.max_total_shell_time_per_session,
        max_output_size_bytes=settings.max_output_size_bytes,
    )


def get_diff_approval_config() -> DiffApprovalConfig:
    """Get computed diff-approval configuration from settings."""
    settings = get_guardrails_settings()

    # In readonly mode, enable diff-first for everything
    if settings.readonly_mode:
        return DiffApprovalConfig(
            enabled=True,
            require_approval_for_writes=True,
            require_approval_for_deletes=True,
            require_approval_for_shell=True,
            approval_timeout_seconds=settings.diff_first_timeout_seconds,
            protected_patterns=["*"],  # All files protected
        )

    patterns = [
        p.strip()
        for p in settings.diff_first_protected_patterns.split(",")
        if p.strip()
    ]

    return DiffApprovalConfig(
        enabled=settings.diff_first_enabled,
        require_approval_for_writes=settings.diff_first_require_writes,
        require_approval_for_deletes=settings.diff_first_require_deletes,
        require_approval_for_shell=settings.diff_first_require_shell,
        approval_timeout_seconds=settings.diff_first_timeout_seconds,
        protected_patterns=patterns,
    )


def get_audit_retention_config() -> AuditRetentionConfig:
    """Get computed audit retention configuration from settings."""
    settings = get_guardrails_settings()

    return AuditRetentionConfig(
        default_retention_days=settings.audit_retention_days,
        policies={
            "audit_logs": settings.audit_retention_days,
            "tool_audit_logs": settings.audit_tool_retention_days,
            "llm_exchange_logs": settings.audit_llm_retention_days,
            "file_change_logs": settings.audit_file_retention_days,
            "budget_logs": settings.audit_budget_retention_days,
        },
        max_diff_size=settings.audit_max_diff_size,
        max_error_size=settings.audit_max_error_size,
        max_content_size=settings.audit_max_content_size,
        max_params_size=settings.audit_max_params_size,
        compress_diffs=settings.audit_compress_diffs,
        compression_threshold=settings.audit_compression_threshold,
        hash_algorithm=settings.audit_hash_algorithm,
        preserve_hash_on_truncate=settings.audit_preserve_hash_on_truncate,
    )


def get_agent_tool_allowlist(agent_id: str) -> list[str] | None:
    """Get tool allowlist for a specific agent.

    Args:
        agent_id: Agent identifier (mo, architect, coder, etc.)

    Returns:
        List of allowed tool names, or None to use default from AGENT_POLICIES
    """
    settings = get_guardrails_settings()

    # In readonly mode, remove write-capable tools
    if settings.readonly_mode:
        readonly_tools = ["filesystem", "web_search", "web_fetch", "sessions"]
        return readonly_tools

    # In sandbox mode, no shell access
    if settings.sandbox_mode:
        # Get from settings, but filter out shell
        pass  # Handled by caller

    tool_map = {
        "mo": settings.mo_allowed_tools,
        "architect": settings.architect_allowed_tools,
        "coder": settings.coder_allowed_tools,
        "reviewer": settings.reviewer_allowed_tools,
        "tester": settings.tester_allowed_tools,
        "docs": settings.docs_allowed_tools,
        "devops": settings.devops_allowed_tools,
    }

    tools_str = tool_map.get(agent_id, "")
    if not tools_str:
        return None  # Use default from AGENT_POLICIES

    tools = [t.strip() for t in tools_str.split(",") if t.strip()]

    # In sandbox mode, filter out shell
    if settings.sandbox_mode and "shell" in tools:
        tools.remove("shell")

    return tools if tools else None


def validate_guardrails_config() -> list[str]:
    """Validate the current guardrails configuration.

    Returns:
        List of validation error messages (empty if valid)
    """
    errors = []
    settings = get_guardrails_settings()

    # Check for conflicting modes
    if settings.readonly_mode and settings.strict_mode:
        logger.warning(
            "Both readonly_mode and strict_mode enabled - "
            "readonly takes precedence for diff-first"
        )

    # Validate retention days make sense
    if settings.audit_llm_retention_days > settings.audit_retention_days:
        errors.append(
            f"audit_llm_retention_days ({settings.audit_llm_retention_days}) > "
            f"audit_retention_days ({settings.audit_retention_days})"
        )

    # Validate size limits make sense
    if settings.audit_compression_threshold > settings.audit_max_diff_size:
        errors.append(
            f"audit_compression_threshold ({settings.audit_compression_threshold}) > "
            f"audit_max_diff_size ({settings.audit_max_diff_size})"
        )

    # Log any errors
    for error in errors:
        logger.error(f"Guardrails config validation error: {error}")

    return errors


def get_config_summary() -> dict[str, Any]:
    """Get a summary of current guardrails configuration for API/diagnostics."""
    settings = get_guardrails_settings()

    return {
        "modes": {
            "strict_mode": settings.strict_mode,
            "readonly_mode": settings.readonly_mode,
            "sandbox_mode": settings.sandbox_mode,
            "diff_first_enabled": settings.diff_first_enabled,
        },
        "budget_limits": {
            "max_tool_loops_per_message": settings.max_tool_loops_per_message,
            "max_tool_calls_per_session": settings.max_tool_calls_per_session,
            "max_spawned_tasks_per_run": settings.max_spawned_tasks_per_run,
            "max_shell_time_seconds": settings.max_shell_time_seconds,
        },
        "audit_retention": {
            "default_days": settings.audit_retention_days,
            "llm_days": settings.audit_llm_retention_days,
            "max_diff_size": settings.audit_max_diff_size,
            "compress_diffs": settings.audit_compress_diffs,
        },
        "validation_errors": validate_guardrails_config(),
    }
