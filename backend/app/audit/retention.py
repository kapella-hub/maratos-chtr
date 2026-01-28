"""Audit log retention and size management.

Provides:
- Configurable retention policies per table
- Size limiting with truncation and hash preservation
- Optional gzip compression for large diffs
- Cleanup utilities for expired records
"""

import base64
import gzip
import hashlib
import logging
from contextlib import nullcontext
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import delete, text, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import (
    async_session_factory,
    AuditLog,
    ToolAuditLog,
    LLMExchangeLog,
    FileChangeLog,
    BudgetLog,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Retention Configuration
# =============================================================================


@dataclass
class TableRetentionPolicy:
    """Retention policy for a specific audit table."""

    table_name: str
    retention_days: int = 90  # Days to keep records
    max_records: int | None = None  # Optional max record count (oldest deleted first)


@dataclass
class RetentionConfig:
    """Global retention configuration."""

    # Per-table policies (table_name -> policy)
    policies: dict[str, TableRetentionPolicy] = field(default_factory=dict)

    # Default retention if no specific policy
    default_retention_days: int = 90

    # Size limits
    max_diff_size: int = 50_000  # 50KB - diffs larger than this get compressed
    max_error_size: int = 10_000  # 10KB max for error messages
    max_content_size: int = 5_000  # 5KB max for redacted content
    max_params_size: int = 10_000  # 10KB max for redacted params JSON

    # Compression settings
    compress_diffs: bool = True
    compression_threshold: int = 1_000  # Compress diffs > 1KB

    @classmethod
    def default(cls) -> "RetentionConfig":
        """Create default retention configuration."""
        return cls(
            policies={
                "audit_logs": TableRetentionPolicy("audit_logs", retention_days=90),
                "tool_audit_logs": TableRetentionPolicy("tool_audit_logs", retention_days=60),
                "llm_exchange_logs": TableRetentionPolicy("llm_exchange_logs", retention_days=30),
                "file_change_logs": TableRetentionPolicy("file_change_logs", retention_days=90),
                "budget_logs": TableRetentionPolicy("budget_logs", retention_days=30),
            }
        )


# Global config instance
_retention_config: RetentionConfig | None = None


def get_retention_config() -> RetentionConfig:
    """Get the global retention configuration."""
    global _retention_config
    if _retention_config is None:
        _retention_config = RetentionConfig.default()
    return _retention_config


def set_retention_config(config: RetentionConfig) -> None:
    """Set the global retention configuration."""
    global _retention_config
    _retention_config = config


# =============================================================================
# Size Limiting and Truncation
# =============================================================================


@dataclass
class TruncatedContent:
    """Result of truncating content."""

    content: str  # Truncated content
    original_hash: str  # SHA256 hash of original
    original_size: int  # Original size in bytes
    was_truncated: bool  # Whether truncation occurred


def truncate_with_hash(
    content: str | None,
    max_size: int,
    preserve_start: int = 500,
    preserve_end: int = 200,
) -> TruncatedContent | None:
    """Truncate content while preserving hash and metadata.

    Args:
        content: Content to truncate
        max_size: Maximum size in characters
        preserve_start: Characters to preserve from start
        preserve_end: Characters to preserve from end

    Returns:
        TruncatedContent with hash and truncated content, or None if input is None
    """
    if content is None:
        return None

    original_size = len(content)
    original_hash = hashlib.sha256(content.encode()).hexdigest()

    if original_size <= max_size:
        return TruncatedContent(
            content=content,
            original_hash=original_hash,
            original_size=original_size,
            was_truncated=False,
        )

    # Truncate with start and end preservation
    truncated = (
        content[:preserve_start]
        + f"\n\n... [{original_size - preserve_start - preserve_end} chars truncated, "
        f"hash: {original_hash[:16]}] ...\n\n"
        + content[-preserve_end:]
    )

    return TruncatedContent(
        content=truncated,
        original_hash=original_hash,
        original_size=original_size,
        was_truncated=True,
    )


def truncate_error(error: str | None, max_size: int = 10_000) -> str | None:
    """Truncate error message preserving start and end."""
    if error is None:
        return None

    result = truncate_with_hash(error, max_size, preserve_start=2000, preserve_end=500)
    return result.content if result else None


def truncate_params(params: dict[str, Any] | None, max_size: int = 10_000) -> dict[str, Any] | None:
    """Truncate large parameter values."""
    if params is None:
        return None

    import json

    result = {}
    current_size = 0

    for key, value in params.items():
        if isinstance(value, str) and len(value) > 500:
            # Truncate long string values
            truncated = truncate_with_hash(value, 500)
            if truncated:
                hash_short = truncated.original_hash[:16]
                result[key] = f"[{truncated.original_size} chars, hash: {hash_short}]"
        else:
            result[key] = value

        # Check total size
        current_size = len(json.dumps(result, default=str))
        if current_size > max_size:
            result[key] = "[TRUNCATED: size limit]"
            break

    return result


# =============================================================================
# Diff Compression
# =============================================================================


@dataclass
class CompressedDiff:
    """Result of compressing a diff."""

    content: str  # Compressed content (base64 if compressed)
    is_compressed: bool
    original_hash: str
    original_size: int
    compressed_size: int


def compress_diff(
    diff: str | None,
    threshold: int = 1_000,
    max_size: int = 50_000,
) -> CompressedDiff | None:
    """Compress diff if it exceeds threshold.

    Args:
        diff: Diff content to compress
        threshold: Compress if larger than this
        max_size: Maximum size after compression/truncation

    Returns:
        CompressedDiff with metadata, or None if input is None
    """
    if diff is None:
        return None

    original_size = len(diff)
    original_hash = hashlib.sha256(diff.encode()).hexdigest()

    # If small enough, no compression needed
    if original_size <= threshold:
        return CompressedDiff(
            content=diff,
            is_compressed=False,
            original_hash=original_hash,
            original_size=original_size,
            compressed_size=original_size,
        )

    # Compress with gzip
    compressed_bytes = gzip.compress(diff.encode("utf-8"), compresslevel=6)
    compressed_b64 = base64.b64encode(compressed_bytes).decode("ascii")

    # Add prefix to indicate compression
    compressed_content = f"GZIP:{compressed_b64}"
    compressed_size = len(compressed_content)

    # If still too large after compression, truncate
    if compressed_size > max_size:
        # Fall back to truncation
        truncated = truncate_with_hash(diff, max_size)
        if truncated:
            return CompressedDiff(
                content=truncated.content,
                is_compressed=False,
                original_hash=original_hash,
                original_size=original_size,
                compressed_size=len(truncated.content),
            )

    return CompressedDiff(
        content=compressed_content,
        is_compressed=True,
        original_hash=original_hash,
        original_size=original_size,
        compressed_size=compressed_size,
    )


def decompress_diff(content: str | None) -> str | None:
    """Decompress a diff if it was compressed.

    Args:
        content: Potentially compressed diff content

    Returns:
        Decompressed diff content
    """
    if content is None:
        return None

    if not content.startswith("GZIP:"):
        return content

    try:
        compressed_b64 = content[5:]  # Remove "GZIP:" prefix
        compressed_bytes = base64.b64decode(compressed_b64)
        return gzip.decompress(compressed_bytes).decode("utf-8")
    except Exception as e:
        logger.warning(f"Failed to decompress diff: {e}")
        return content  # Return as-is if decompression fails


# =============================================================================
# Retention Cleanup
# =============================================================================


@dataclass
class CleanupResult:
    """Result of a cleanup operation."""

    table_name: str
    deleted_count: int
    cutoff_date: datetime
    error: str | None = None


@dataclass
class FullCleanupResult:
    """Result of cleaning up all tables."""

    results: list[CleanupResult]
    total_deleted: int
    vacuum_run: bool
    analyze_run: bool


async def purge_old_records(
    table_name: str,
    retention_days: int,
    db: AsyncSession | None = None,
) -> CleanupResult:
    """Purge records older than retention_days from a specific table.

    Args:
        table_name: Name of the table to clean
        retention_days: Delete records older than this many days
        db: Optional database session (creates one if not provided)

    Returns:
        CleanupResult with count of deleted records
    """
    cutoff_date = datetime.utcnow() - timedelta(days=retention_days)

    table_map = {
        "audit_logs": AuditLog,
        "tool_audit_logs": ToolAuditLog,
        "llm_exchange_logs": LLMExchangeLog,
        "file_change_logs": FileChangeLog,
        "budget_logs": BudgetLog,
    }

    table_class = table_map.get(table_name)
    if not table_class:
        return CleanupResult(
            table_name=table_name,
            deleted_count=0,
            cutoff_date=cutoff_date,
            error=f"Unknown table: {table_name}",
        )

    try:
        if db:
            session = db
            should_commit = False
        else:
            session = async_session_factory()
            should_commit = True

        async with session if should_commit else nullcontext(session):
            # Delete old records
            stmt = delete(table_class).where(table_class.created_at < cutoff_date)
            result = await session.execute(stmt)
            deleted_count = result.rowcount

            if should_commit:
                await session.commit()

            logger.info(
                f"Purged {deleted_count} records from {table_name} "
                f"older than {retention_days} days"
            )

            return CleanupResult(
                table_name=table_name,
                deleted_count=deleted_count,
                cutoff_date=cutoff_date,
            )

    except Exception as e:
        logger.error(f"Error purging {table_name}: {e}")
        return CleanupResult(
            table_name=table_name,
            deleted_count=0,
            cutoff_date=cutoff_date,
            error=str(e),
        )


# Note: nullcontext imported at top of file


async def purge_all_tables(
    config: RetentionConfig | None = None,
    run_vacuum: bool = True,
    run_analyze: bool = True,
) -> FullCleanupResult:
    """Purge old records from all audit tables based on retention policy.

    Args:
        config: Retention configuration (uses default if not provided)
        run_vacuum: Whether to run VACUUM after deletion (SQLite)
        run_analyze: Whether to run ANALYZE after deletion

    Returns:
        FullCleanupResult with per-table results
    """
    config = config or get_retention_config()
    results = []
    total_deleted = 0

    # Process each table
    for table_name, policy in config.policies.items():
        result = await purge_old_records(table_name, policy.retention_days)
        results.append(result)
        total_deleted += result.deleted_count

    # Run VACUUM and ANALYZE if requested (for SQLite)
    vacuum_success = False
    analyze_success = False

    if run_vacuum or run_analyze:
        try:
            async with async_session_factory() as session:
                if run_vacuum:
                    # VACUUM requires autocommit mode in SQLite
                    await session.execute(text("VACUUM"))
                    vacuum_success = True
                    logger.info("VACUUM completed successfully")

                if run_analyze:
                    await session.execute(text("ANALYZE"))
                    analyze_success = True
                    logger.info("ANALYZE completed successfully")

                await session.commit()

        except Exception as e:
            logger.warning(f"Post-cleanup optimization failed: {e}")

    return FullCleanupResult(
        results=results,
        total_deleted=total_deleted,
        vacuum_run=vacuum_success,
        analyze_run=analyze_success,
    )


async def get_table_stats() -> dict[str, dict[str, Any]]:
    """Get statistics for all audit tables.

    Returns:
        Dict mapping table name to stats (count, oldest, newest, size estimate)
    """
    stats = {}

    table_map = {
        "audit_logs": AuditLog,
        "tool_audit_logs": ToolAuditLog,
        "llm_exchange_logs": LLMExchangeLog,
        "file_change_logs": FileChangeLog,
        "budget_logs": BudgetLog,
    }

    async with async_session_factory() as session:
        for table_name, table_class in table_map.items():
            try:
                # Get count
                count_result = await session.execute(
                    select(func.count(table_class.id))
                )
                count = count_result.scalar() or 0

                # Get oldest and newest
                oldest_result = await session.execute(
                    select(func.min(table_class.created_at))
                )
                oldest = oldest_result.scalar()

                newest_result = await session.execute(
                    select(func.max(table_class.created_at))
                )
                newest = newest_result.scalar()

                stats[table_name] = {
                    "count": count,
                    "oldest": oldest.isoformat() if oldest else None,
                    "newest": newest.isoformat() if newest else None,
                }

            except Exception as e:
                stats[table_name] = {"error": str(e)}

    return stats


# =============================================================================
# Helper for processing content before storage
# =============================================================================


def prepare_audit_content(
    diff: str | None = None,
    error: str | None = None,
    content_redacted: str | None = None,
    params_redacted: dict | None = None,
    config: RetentionConfig | None = None,
) -> dict[str, Any]:
    """Prepare audit content with truncation and compression.

    Args:
        diff: Diff content to process
        error: Error message to process
        content_redacted: Redacted content to process
        params_redacted: Redacted parameters to process
        config: Retention configuration

    Returns:
        Dict with processed content and metadata
    """
    config = config or get_retention_config()
    result = {}

    # Process diff with compression
    if diff is not None:
        if config.compress_diffs:
            compressed = compress_diff(
                diff,
                threshold=config.compression_threshold,
                max_size=config.max_diff_size,
            )
            if compressed:
                result["diff"] = compressed.content
                result["diff_compressed"] = compressed.is_compressed
                result["diff_original_size"] = compressed.original_size
                result["diff_original_hash"] = compressed.original_hash
        else:
            truncated = truncate_with_hash(diff, config.max_diff_size)
            if truncated:
                result["diff"] = truncated.content
                result["diff_original_size"] = truncated.original_size
                result["diff_original_hash"] = truncated.original_hash

    # Process error
    if error is not None:
        result["error"] = truncate_error(error, config.max_error_size)

    # Process redacted content
    if content_redacted is not None:
        truncated = truncate_with_hash(content_redacted, config.max_content_size)
        if truncated:
            result["content_redacted"] = truncated.content

    # Process redacted params
    if params_redacted is not None:
        result["parameters_redacted"] = truncate_params(params_redacted, config.max_params_size)

    return result
