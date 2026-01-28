"""Audit event models and types."""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Any
import hashlib
import json


class AuditCategory(str, Enum):
    """Categories of audit events."""
    CHAT = "chat"
    AGENT = "agent"
    TOOL = "tool"
    FILE = "file"
    SYSTEM = "system"
    SECURITY = "security"


class AuditSeverity(str, Enum):
    """Severity levels for audit events."""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class AuditEvent:
    """Base audit event."""

    category: AuditCategory
    action: str
    severity: AuditSeverity = AuditSeverity.INFO
    session_id: str | None = None
    user_id: str | None = None
    agent_id: str | None = None
    task_id: str | None = None
    parent_task_id: str | None = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    duration_ms: float | None = None
    success: bool = True
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        d = asdict(self)
        d["category"] = self.category.value
        d["severity"] = self.severity.value
        d["timestamp"] = self.timestamp.isoformat()
        return d

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), default=str)


@dataclass
class ChatAuditEvent(AuditEvent):
    """Audit event for chat requests/responses."""

    category: AuditCategory = field(default=AuditCategory.CHAT, init=False)
    message_hash: str | None = None  # SHA256 of message content
    message_length: int = 0
    response_length: int = 0
    model: str | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None

    @staticmethod
    def hash_content(content: str) -> str:
        """Create SHA256 hash of content for audit without storing PII."""
        return hashlib.sha256(content.encode()).hexdigest()[:16]


@dataclass
class AgentAuditEvent(AuditEvent):
    """Audit event for agent operations."""

    category: AuditCategory = field(default=AuditCategory.AGENT, init=False)
    spawn_reason: str | None = None
    goals_total: int = 0
    goals_completed: int = 0
    goals_failed: int = 0
    checkpoints: list[str] = field(default_factory=list)
    nested_spawns: int = 0


@dataclass
class ToolAuditEvent(AuditEvent):
    """Audit event for tool executions."""

    category: AuditCategory = field(default=AuditCategory.TOOL, init=False)
    tool_name: str = ""
    tool_action: str | None = None
    parameters_hash: str | None = None  # Hash of params, not actual values
    output_length: int = 0
    sandbox_violation: bool = False

    @staticmethod
    def hash_params(params: dict[str, Any]) -> str:
        """Create hash of parameters for audit."""
        param_str = json.dumps(params, sort_keys=True, default=str)
        return hashlib.sha256(param_str.encode()).hexdigest()[:16]


@dataclass
class FileAuditEvent(AuditEvent):
    """Audit event for file operations."""

    category: AuditCategory = field(default=AuditCategory.FILE, init=False)
    file_path: str = ""
    operation: str = ""  # read, write, delete, copy
    file_size: int | None = None
    in_workspace: bool = True
    blocked: bool = False
