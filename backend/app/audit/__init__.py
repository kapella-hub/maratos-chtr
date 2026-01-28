"""Audit logging system for MaratOS.

Provides structured audit logging for:
- Chat requests and responses
- Agent spawns and completions
- Tool executions
- File operations
- System events

Includes retention and performance features:
- Configurable retention policies per table
- Size limiting with truncation and hash preservation
- Optional gzip compression for large diffs
- Compound indexes for common query patterns
"""

from app.audit.models import (
    AuditEvent,
    AuditCategory,
    AuditSeverity,
    ChatAuditEvent,
    AgentAuditEvent,
    ToolAuditEvent,
    FileAuditEvent,
)
from app.audit.logger import AuditLogger, audit_logger
from app.audit.retention import (
    RetentionConfig,
    TableRetentionPolicy,
    get_retention_config,
    set_retention_config,
    purge_old_records,
    purge_all_tables,
    get_table_stats,
    compress_diff,
    decompress_diff,
    truncate_with_hash,
    truncate_error,
    truncate_params,
)

__all__ = [
    # Event models
    "AuditEvent",
    "AuditCategory",
    "AuditSeverity",
    "ChatAuditEvent",
    "AgentAuditEvent",
    "ToolAuditEvent",
    "FileAuditEvent",
    # Logger
    "AuditLogger",
    "audit_logger",
    # Retention
    "RetentionConfig",
    "TableRetentionPolicy",
    "get_retention_config",
    "set_retention_config",
    "purge_old_records",
    "purge_all_tables",
    "get_table_stats",
    # Compression/truncation
    "compress_diff",
    "decompress_diff",
    "truncate_with_hash",
    "truncate_error",
    "truncate_params",
]
