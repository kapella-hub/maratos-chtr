"""Database setup and session management."""

import logging
from datetime import datetime
from typing import AsyncGenerator

from sqlalchemy import Boolean, Float, JSON, DateTime, Index, Integer, String, Text, UniqueConstraint, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.config import settings

logger = logging.getLogger(__name__)

# Current schema version - increment when making schema changes
SCHEMA_VERSION = 5  # v1 = original, v2 = orchestration tables, v3 = channel unification, v4 = audit logs, v5 = audit performance indexes


class Base(DeclarativeBase):
    """Base class for all models."""

    pass


class SchemaVersion(Base):
    """Tracks database schema version for safe migrations."""

    __tablename__ = "schema_version"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    version: Mapped[int] = mapped_column(Integer, default=1)
    applied_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)


class Session(Base):
    """Chat session model.

    Unified session for both web UI and external channels (Telegram, iMessage, Webex).
    """

    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    agent_id: Mapped[str] = mapped_column(String(50), default="default")
    title: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    # Inline project tracking (for unified chat + autonomous)
    inline_project_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    inline_project_status: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Active project context
    active_project_name: Mapped[str | None] = mapped_column(String(100), nullable=True)  # Currently loaded project

    # Channel unification fields
    channel_type: Mapped[str] = mapped_column(String(20), default="web", index=True)  # web, telegram, imessage, webex
    external_thread_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)  # Platform-specific thread/chat ID
    channel_user_id: Mapped[str | None] = mapped_column(String(100), nullable=True)  # Platform-specific user ID
    channel_user_name: Mapped[str | None] = mapped_column(String(200), nullable=True)  # Display name from channel


class Message(Base):
    """Chat message model.

    Stores messages from all channels with source tracking for unified history.
    """

    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(36), index=True)
    role: Mapped[str] = mapped_column(String(20))  # user, assistant, system, tool
    content: Mapped[str] = mapped_column(Text)
    tool_calls: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    thinking_data: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON string for thinking blocks
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Channel source tracking
    source_channel: Mapped[str] = mapped_column(String(20), default="web")  # web, telegram, imessage, webex
    external_message_id: Mapped[str | None] = mapped_column(String(100), nullable=True)  # Platform-specific message ID
    sender_id: Mapped[str | None] = mapped_column(String(100), nullable=True)  # Platform-specific sender ID
    sender_name: Mapped[str | None] = mapped_column(String(200), nullable=True)  # Display name
    attachments: Mapped[list | None] = mapped_column(JSON, nullable=True)  # List of attachment metadata
    redacted: Mapped[bool] = mapped_column(Boolean, default=False)  # Whether content was redacted


class ChannelThreadMapping(Base):
    """Maps external channel threads to internal sessions.

    Enables fast lookup: given (channel_type, external_thread_id) -> session_id.
    One external thread maps to exactly one session.
    """

    __tablename__ = "channel_thread_mappings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    channel_type: Mapped[str] = mapped_column(String(20), index=True)  # telegram, imessage, webex
    external_thread_id: Mapped[str] = mapped_column(String(100), index=True)  # Platform-specific chat/thread ID
    session_id: Mapped[str] = mapped_column(String(36), index=True)  # References sessions.id
    channel_user_id: Mapped[str | None] = mapped_column(String(100), nullable=True)  # Primary user in thread
    channel_user_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_message_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Unique constraint: one session per channel+thread combination
    __table_args__ = (
        UniqueConstraint("channel_type", "external_thread_id", name="uq_channel_thread"),
    )


class Memory(Base):
    """Long-term memory storage."""

    __tablename__ = "memories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list | None] = mapped_column(JSON, nullable=True)
    extra_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AutonomousProject(Base):
    """Autonomous development project."""

    __tablename__ = "autonomous_projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    original_prompt: Mapped[str] = mapped_column(Text)
    workspace_path: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20), default="planning")
    config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    branch_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    pr_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    total_iterations: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    paused_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AutonomousTask(Base):
    """Task within an autonomous project."""

    __tablename__ = "autonomous_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    agent_type: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    depends_on: Mapped[list | None] = mapped_column(JSON, nullable=True)
    quality_gates: Mapped[list | None] = mapped_column(JSON, nullable=True)
    iterations: Mapped[list | None] = mapped_column(JSON, nullable=True)
    target_files: Mapped[list | None] = mapped_column(JSON, nullable=True)
    max_attempts: Mapped[int] = mapped_column(default=3)
    priority: Mapped[int] = mapped_column(default=0)
    final_commit_sha: Mapped[str | None] = mapped_column(String(40), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class CanvasArtifact(Base):
    """Visual artifacts created by agents in the canvas workspace."""

    __tablename__ = "canvas_artifacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(36), index=True)
    message_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    artifact_type: Mapped[str] = mapped_column(String(20))  # code, preview, form, chart, diagram, table, diff, terminal
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text)
    extra_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # language, editable, etc.
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class SubagentTaskRecord(Base):
    """Persistent storage for subagent tasks (for restart recovery)."""

    __tablename__ = "subagent_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    agent_id: Mapped[str] = mapped_column(String(50), index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    progress: Mapped[float] = mapped_column(default=0.0)

    # Session context for restart
    callback_session: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    parent_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    # Timing
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Results and state
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    logs: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # Goals and checkpoints for recovery
    goals: Mapped[list | None] = mapped_column(JSON, nullable=True)
    checkpoints: Mapped[list | None] = mapped_column(JSON, nullable=True)
    response_so_far: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Retry tracking
    attempt: Mapped[int] = mapped_column(default=1)
    max_attempts: Mapped[int] = mapped_column(default=3)

    # Fallback tracking
    fallback_agent_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    original_task_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


# =============================================================================
# Orchestration Engine Persistence Models
# =============================================================================


class OrchestrationRun(Base):
    """Orchestration run metadata for durability and auditability.

    Stores run state so long-running agent builds survive restarts.
    """

    __tablename__ = "orchestration_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)

    # Context
    original_prompt: Mapped[str] = mapped_column(Text)
    workspace_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)

    # Run mode: "inline" (chat project mode) or "autonomous" (API-driven)
    mode: Mapped[str] = mapped_column(String(20), default="inline")

    # State machine state
    state: Mapped[str] = mapped_column(String(20), default="intake", index=True)
    resume_state: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Plan JSON (full ExecutionPlan serialized)
    plan_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Task graph state (serialized graph for resume)
    graph_state: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Config
    config_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Error tracking
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_details: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    paused_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class OrchestrationTask(Base):
    """Task within an orchestration run (task graph node).

    Persists task state including dependencies, status, and results.
    """

    __tablename__ = "orchestration_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(36), index=True)

    # Task definition (from PlannedTask)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    agent_id: Mapped[str] = mapped_column(String(50), index=True)
    skill_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Dependencies (list of task IDs)
    depends_on: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # Target files
    target_files: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # Acceptance criteria (list of AcceptanceCriterion dicts)
    acceptance_criteria: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # Status tracking
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    attempt: Mapped[int] = mapped_column(default=1)
    max_attempts: Mapped[int] = mapped_column(default=3)
    priority: Mapped[int] = mapped_column(default=0)

    # Results
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    verification_results: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class TaskLog(Base):
    """Log entries and tool audit trail for orchestration tasks.

    Provides detailed audit trail for debugging and compliance.
    """

    __tablename__ = "task_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_id: Mapped[str] = mapped_column(String(36), index=True)
    run_id: Mapped[str] = mapped_column(String(36), index=True)

    # Log entry
    level: Mapped[str] = mapped_column(String(10), default="info")  # debug, info, warning, error
    message: Mapped[str] = mapped_column(Text)

    # Tool audit trail (optional)
    tool_name: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    tool_input: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    tool_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    tool_duration_ms: Mapped[float | None] = mapped_column(nullable=True)

    # Timestamp
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class TaskArtifact(Base):
    """Artifacts produced by orchestration tasks.

    Tracks files, outputs, and other artifacts for provenance.
    """

    __tablename__ = "task_artifacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_id: Mapped[str] = mapped_column(String(36), index=True)
    run_id: Mapped[str] = mapped_column(String(36), index=True)

    # Artifact metadata
    name: Mapped[str] = mapped_column(String(200))
    artifact_type: Mapped[str] = mapped_column(String(50))  # file, code, data, report, etc.
    path: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Content (for small artifacts; large ones use path)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)  # SHA-256

    # Extra metadata
    extra_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Producer tracking
    producer_agent: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Timestamp
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# =============================================================================
# Audit Log Persistence Models
# =============================================================================


class AuditLog(Base):
    """Base audit log entry for all auditable events.

    Stores comprehensive audit trail for compliance and debugging.
    """

    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)

    # Event classification
    category: Mapped[str] = mapped_column(String(20), index=True)  # chat, agent, tool, file, security
    action: Mapped[str] = mapped_column(String(50), index=True)
    severity: Mapped[str] = mapped_column(String(10), default="info", index=True)  # debug, info, warning, error, critical

    # Context
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    task_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    agent_id: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    user_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Outcome
    success: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Additional data (JSON) - named extra_data to avoid SQLAlchemy reserved name
    extra_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)

    # Compound indexes for common query patterns
    __table_args__ = (
        Index("ix_audit_logs_session_created", "session_id", "created_at"),
        Index("ix_audit_logs_category_created", "category", "created_at"),
        Index("ix_audit_logs_agent_created", "agent_id", "created_at"),
        Index("ix_audit_logs_severity_created", "severity", "created_at"),
    )


class ToolAuditLog(Base):
    """Audit log for tool invocations.

    Stores tool calls and results with parameter hashes (not raw values)
    for security while maintaining audit trail.
    """

    __tablename__ = "tool_audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)

    # Context
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    task_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    agent_id: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)

    # Tool info
    tool_name: Mapped[str] = mapped_column(String(50), index=True)
    tool_action: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Parameters (hashed for privacy)
    parameters_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    parameters_redacted: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # Redacted params for debugging

    # Outcome
    success: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    output_length: Mapped[int] = mapped_column(Integer, default=0)
    output_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[float] = mapped_column(Float, default=0.0)

    # Security flags
    sandbox_violation: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    budget_exceeded: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    policy_blocked: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)

    # Compound indexes for common query patterns
    __table_args__ = (
        Index("ix_tool_audit_session_created", "session_id", "created_at"),
        Index("ix_tool_audit_tool_created", "tool_name", "created_at"),
        Index("ix_tool_audit_agent_tool", "agent_id", "tool_name"),
        Index("ix_tool_audit_security", "sandbox_violation", "budget_exceeded", "policy_blocked"),
    )


class LLMExchangeLog(Base):
    """Audit log for LLM prompt/response exchanges.

    Stores either hashed content (privacy mode) or full content
    (debugging mode) based on configuration.
    """

    __tablename__ = "llm_exchange_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)

    # Context
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    task_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    agent_id: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)

    # Exchange type
    exchange_type: Mapped[str] = mapped_column(String(20), index=True)  # request, response, error

    # Model info
    model: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)

    # Content (configurable: hash-only or full)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    content_length: Mapped[int] = mapped_column(Integer, default=0)
    content_redacted: Mapped[str | None] = mapped_column(Text, nullable=True)  # Optional redacted content

    # Token usage
    tokens_in: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_out: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Outcome
    success: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)

    # Compound indexes for common query patterns
    __table_args__ = (
        Index("ix_llm_exchange_session_created", "session_id", "created_at"),
        Index("ix_llm_exchange_model_created", "model", "created_at"),
        Index("ix_llm_exchange_type_created", "exchange_type", "created_at"),
    )


class FileChangeLog(Base):
    """Audit log for file operations with diff tracking.

    Stores file operation details including content hashes and
    optional diffs for change tracking.
    """

    __tablename__ = "file_change_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)

    # Context
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    task_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    agent_id: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)

    # File info
    file_path: Mapped[str] = mapped_column(String(500), index=True)
    operation: Mapped[str] = mapped_column(String(20), index=True)  # read, write, delete, copy

    # Content tracking
    before_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    after_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Diff (optional, for writes) - may be gzip compressed (prefixed with "GZIP:")
    diff: Mapped[str | None] = mapped_column(Text, nullable=True)
    diff_lines_added: Mapped[int | None] = mapped_column(Integer, nullable=True)
    diff_lines_removed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Diff metadata for compressed/truncated diffs
    diff_original_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    diff_original_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Security flags
    in_workspace: Mapped[bool] = mapped_column(Boolean, default=True)
    blocked: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    approval_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)

    # Outcome
    success: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)

    # Compound indexes for common query patterns
    __table_args__ = (
        Index("ix_file_change_session_created", "session_id", "created_at"),
        Index("ix_file_change_path_created", "file_path", "created_at"),
        Index("ix_file_change_operation_created", "operation", "created_at"),
        Index("ix_file_change_approval", "approval_id", "created_at"),
    )


class BudgetLog(Base):
    """Audit log for budget tracking and enforcement.

    Tracks budget usage and violations for monitoring and alerting.
    """

    __tablename__ = "budget_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)

    # Context
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    task_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    agent_id: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)

    # Budget type
    budget_type: Mapped[str] = mapped_column(String(30), index=True)  # tool_loops, shell_time, spawned_tasks, etc.

    # Usage
    current_value: Mapped[float] = mapped_column(Float, default=0.0)
    limit_value: Mapped[float] = mapped_column(Float, default=0.0)
    exceeded: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)

    # Compound indexes for common query patterns
    __table_args__ = (
        Index("ix_budget_session_created", "session_id", "created_at"),
        Index("ix_budget_agent_type", "agent_id", "budget_type"),
        Index("ix_budget_exceeded_created", "exceeded", "created_at"),
    )


# Engine and session factory
engine = create_async_engine(settings.database_url, echo=settings.debug)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def _migrate_sessions_table(conn) -> None:
    """Add missing columns to sessions table if needed."""
    # Check which columns exist
    result = await conn.execute(text("PRAGMA table_info(sessions)"))
    existing_columns = {row[1] for row in result.fetchall()}

    # Columns that should exist
    migrations = [
        ("channel_type", "ALTER TABLE sessions ADD COLUMN channel_type VARCHAR(20) DEFAULT 'web'"),
        ("external_thread_id", "ALTER TABLE sessions ADD COLUMN external_thread_id VARCHAR(100)"),
        ("channel_user_id", "ALTER TABLE sessions ADD COLUMN channel_user_id VARCHAR(100)"),
        ("channel_user_name", "ALTER TABLE sessions ADD COLUMN channel_user_name VARCHAR(200)"),
        ("active_project_name", "ALTER TABLE sessions ADD COLUMN active_project_name VARCHAR(100)"),
    ]

    for col_name, sql in migrations:
        if col_name not in existing_columns:
            logger.info(f"Adding missing column: sessions.{col_name}")
            await conn.execute(text(sql))


async def _migrate_messages_table(conn) -> None:
    """Add missing columns to messages table if needed."""
    result = await conn.execute(text("PRAGMA table_info(messages)"))
    existing_columns = {row[1] for row in result.fetchall()}

    migrations = [
        ("source_channel", "ALTER TABLE messages ADD COLUMN source_channel VARCHAR(20) DEFAULT 'web'"),
        ("external_message_id", "ALTER TABLE messages ADD COLUMN external_message_id VARCHAR(100)"),
        ("sender_id", "ALTER TABLE messages ADD COLUMN sender_id VARCHAR(100)"),
        ("sender_name", "ALTER TABLE messages ADD COLUMN sender_name VARCHAR(200)"),
        ("attachments", "ALTER TABLE messages ADD COLUMN attachments JSON"),
        ("redacted", "ALTER TABLE messages ADD COLUMN redacted BOOLEAN DEFAULT 0"),
    ]

    for col_name, sql in migrations:
        if col_name not in existing_columns:
            logger.info(f"Adding missing column: messages.{col_name}")
            await conn.execute(text(sql))


async def init_db() -> None:
    """Initialize database tables with safe schema versioning.

    Uses create_all which is idempotent - only creates tables that don't exist.
    Tracks schema version for future migrations.
    """
    settings.data_dir.mkdir(parents=True, exist_ok=True)

    async with engine.begin() as conn:
        # Create all tables (idempotent - won't modify existing tables)
        await conn.run_sync(Base.metadata.create_all)

        # Run migrations for existing tables
        await _migrate_sessions_table(conn)
        await _migrate_messages_table(conn)

    # Check and update schema version
    async with async_session_factory() as session:
        try:
            result = await session.execute(select(SchemaVersion).limit(1))
            version_record = result.scalar_one_or_none()

            if version_record is None:
                # First time initialization
                version_record = SchemaVersion(
                    id=1,
                    version=SCHEMA_VERSION,
                    description=f"Initial schema v{SCHEMA_VERSION}",
                )
                session.add(version_record)
                await session.commit()
                logger.info(f"Database initialized with schema version {SCHEMA_VERSION}")
            elif version_record.version < SCHEMA_VERSION:
                # Schema upgrade needed
                old_version = version_record.version
                version_record.version = SCHEMA_VERSION
                version_record.applied_at = datetime.utcnow()
                version_record.description = f"Upgraded from v{old_version} to v{SCHEMA_VERSION}"
                await session.commit()
                logger.info(f"Database schema upgraded from v{old_version} to v{SCHEMA_VERSION}")
            else:
                logger.debug(f"Database schema is current (v{version_record.version})")
        except Exception as e:
            logger.warning(f"Schema version check failed (may be first run): {e}")
            await session.rollback()


async def get_schema_version() -> int:
    """Get the current database schema version."""
    async with async_session_factory() as session:
        try:
            result = await session.execute(select(SchemaVersion).limit(1))
            version_record = result.scalar_one_or_none()
            return version_record.version if version_record else 0
        except Exception:
            return 0


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for getting database sessions."""
    async with async_session_factory() as session:
        yield session


async def close_db() -> None:
    """Close database connections gracefully."""
    await engine.dispose()
