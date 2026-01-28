"""Audit log repository for database persistence.

Provides async CRUD operations for audit logs with query support.
Includes size limiting, compression, and retention support.
"""

import hashlib
import json
import logging
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import (
    async_session_factory,
    AuditLog,
    ToolAuditLog,
    LLMExchangeLog,
    FileChangeLog,
    BudgetLog,
)
from app.audit.retention import (
    truncate_error,
    truncate_params,
    compress_diff,
    decompress_diff,
    get_retention_config,
)

logger = logging.getLogger(__name__)


def _hash_content(content: str) -> str:
    """Create SHA256 hash of content."""
    return hashlib.sha256(content.encode()).hexdigest()


def _redact_params(params: dict[str, Any]) -> dict[str, Any]:
    """Redact sensitive parameters for audit logging.

    Uses size limiting from retention config to prevent large params
    from bloating the database.
    """
    sensitive_keys = {
        "content", "password", "token", "secret", "key", "api_key",
        "authorization", "credentials", "private_key",
    }

    redacted = {}
    for key, value in params.items():
        key_lower = key.lower()
        if any(s in key_lower for s in sensitive_keys):
            if isinstance(value, str):
                redacted[key] = f"[REDACTED:{len(value)} chars]"
            else:
                redacted[key] = "[REDACTED]"
        elif isinstance(value, str) and len(value) > 200:
            redacted[key] = f"{value[:100]}...[{len(value)} chars total]"
        else:
            redacted[key] = value

    # Apply size limiting from retention config
    config = get_retention_config()
    return truncate_params(redacted, config.max_params_size) or redacted


class AuditRepository:
    """Repository for audit log persistence."""

    # =========================================================================
    # Generic Audit Log
    # =========================================================================

    @staticmethod
    async def log_event(
        category: str,
        action: str,
        session_id: str | None = None,
        task_id: str | None = None,
        agent_id: str | None = None,
        user_id: str | None = None,
        success: bool = True,
        error: str | None = None,
        duration_ms: float | None = None,
        severity: str = "info",
        metadata: dict[str, Any] | None = None,
        db: AsyncSession | None = None,
    ) -> AuditLog:
        """Log a generic audit event."""
        log_entry = AuditLog(
            id=str(uuid.uuid4()),
            category=category,
            action=action,
            session_id=session_id,
            task_id=task_id,
            agent_id=agent_id,
            user_id=user_id,
            success=success,
            error=error,
            duration_ms=duration_ms,
            severity=severity,
            extra_data=metadata,
        )

        if db:
            db.add(log_entry)
        else:
            async with async_session_factory() as session:
                session.add(log_entry)
                await session.commit()

        return log_entry

    # =========================================================================
    # Tool Audit Log
    # =========================================================================

    @staticmethod
    async def log_tool_call(
        tool_name: str,
        tool_action: str | None = None,
        parameters: dict[str, Any] | None = None,
        session_id: str | None = None,
        task_id: str | None = None,
        agent_id: str | None = None,
        db: AsyncSession | None = None,
    ) -> ToolAuditLog:
        """Log a tool call (before execution)."""
        params = parameters or {}
        params_hash = _hash_content(json.dumps(params, sort_keys=True, default=str))
        params_redacted = _redact_params(params)

        log_entry = ToolAuditLog(
            id=str(uuid.uuid4()),
            session_id=session_id,
            task_id=task_id,
            agent_id=agent_id,
            tool_name=tool_name,
            tool_action=tool_action,
            parameters_hash=params_hash,
            parameters_redacted=params_redacted,
        )

        if db:
            db.add(log_entry)
        else:
            async with async_session_factory() as session:
                session.add(log_entry)
                await session.commit()

        return log_entry

    @staticmethod
    async def log_tool_result(
        log_id: str,
        success: bool,
        output: str | None = None,
        error: str | None = None,
        duration_ms: float = 0.0,
        sandbox_violation: bool = False,
        budget_exceeded: bool = False,
        policy_blocked: bool = False,
        db: AsyncSession | None = None,
    ) -> bool:
        """Update a tool log with execution results."""
        async with async_session_factory() as session:
            result = await session.execute(
                select(ToolAuditLog).where(ToolAuditLog.id == log_id)
            )
            log_entry = result.scalar_one_or_none()

            if not log_entry:
                return False

            log_entry.success = success
            log_entry.output_length = len(output) if output else 0
            log_entry.output_hash = _hash_content(output) if output else None
            log_entry.error = error
            log_entry.duration_ms = duration_ms
            log_entry.sandbox_violation = sandbox_violation
            log_entry.budget_exceeded = budget_exceeded
            log_entry.policy_blocked = policy_blocked

            await session.commit()
            return True

    # =========================================================================
    # LLM Exchange Log
    # =========================================================================

    @staticmethod
    async def log_llm_request(
        content: str,
        model: str | None = None,
        session_id: str | None = None,
        task_id: str | None = None,
        agent_id: str | None = None,
        include_content: bool = False,
        db: AsyncSession | None = None,
    ) -> LLMExchangeLog:
        """Log an LLM request."""
        log_entry = LLMExchangeLog(
            id=str(uuid.uuid4()),
            session_id=session_id,
            task_id=task_id,
            agent_id=agent_id,
            exchange_type="request",
            model=model,
            content_hash=_hash_content(content),
            content_length=len(content),
            content_redacted=content[:1000] + "..." if include_content and len(content) > 1000 else (content if include_content else None),
        )

        if db:
            db.add(log_entry)
        else:
            async with async_session_factory() as session:
                session.add(log_entry)
                await session.commit()

        return log_entry

    @staticmethod
    async def log_llm_response(
        content: str,
        model: str | None = None,
        tokens_in: int | None = None,
        tokens_out: int | None = None,
        duration_ms: float | None = None,
        success: bool = True,
        error: str | None = None,
        session_id: str | None = None,
        task_id: str | None = None,
        agent_id: str | None = None,
        include_content: bool = False,
        db: AsyncSession | None = None,
    ) -> LLMExchangeLog:
        """Log an LLM response."""
        log_entry = LLMExchangeLog(
            id=str(uuid.uuid4()),
            session_id=session_id,
            task_id=task_id,
            agent_id=agent_id,
            exchange_type="response",
            model=model,
            content_hash=_hash_content(content),
            content_length=len(content),
            content_redacted=content[:1000] + "..." if include_content and len(content) > 1000 else (content if include_content else None),
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            duration_ms=duration_ms,
            success=success,
            error=error,
        )

        if db:
            db.add(log_entry)
        else:
            async with async_session_factory() as session:
                session.add(log_entry)
                await session.commit()

        return log_entry

    # =========================================================================
    # File Change Log
    # =========================================================================

    @staticmethod
    async def log_file_operation(
        file_path: str,
        operation: str,
        before_content: str | None = None,
        after_content: str | None = None,
        diff: str | None = None,
        in_workspace: bool = True,
        blocked: bool = False,
        requires_approval: bool = False,
        approval_id: str | None = None,
        success: bool = True,
        error: str | None = None,
        session_id: str | None = None,
        task_id: str | None = None,
        agent_id: str | None = None,
        db: AsyncSession | None = None,
    ) -> FileChangeLog:
        """Log a file operation with optional diff compression."""
        config = get_retention_config()

        # Calculate diff stats if diff provided (before compression)
        diff_lines_added = None
        diff_lines_removed = None
        diff_original_size = None
        diff_original_hash = None
        processed_diff = diff

        if diff:
            diff_lines_added = sum(1 for line in diff.split("\n") if line.startswith("+") and not line.startswith("+++"))
            diff_lines_removed = sum(1 for line in diff.split("\n") if line.startswith("-") and not line.startswith("---"))

            # Compress diff if configured
            if config.compress_diffs:
                compressed = compress_diff(
                    diff,
                    threshold=config.compression_threshold,
                    max_size=config.max_diff_size,
                )
                if compressed:
                    processed_diff = compressed.content
                    diff_original_size = compressed.original_size
                    diff_original_hash = compressed.original_hash

        # Truncate error if too large
        processed_error = truncate_error(error, config.max_error_size) if error else None

        log_entry = FileChangeLog(
            id=str(uuid.uuid4()),
            session_id=session_id,
            task_id=task_id,
            agent_id=agent_id,
            file_path=file_path,
            operation=operation,
            before_hash=_hash_content(before_content) if before_content else None,
            after_hash=_hash_content(after_content) if after_content else None,
            file_size=len(after_content) if after_content else (len(before_content) if before_content else None),
            diff=processed_diff,
            diff_lines_added=diff_lines_added,
            diff_lines_removed=diff_lines_removed,
            diff_original_size=diff_original_size,
            diff_original_hash=diff_original_hash,
            in_workspace=in_workspace,
            blocked=blocked,
            requires_approval=requires_approval,
            approval_id=approval_id,
            success=success,
            error=processed_error,
        )

        if db:
            db.add(log_entry)
        else:
            async with async_session_factory() as session:
                session.add(log_entry)
                await session.commit()

        return log_entry

    # =========================================================================
    # Budget Log
    # =========================================================================

    @staticmethod
    async def log_budget_check(
        budget_type: str,
        current_value: float,
        limit_value: float,
        exceeded: bool = False,
        session_id: str | None = None,
        task_id: str | None = None,
        agent_id: str | None = None,
        db: AsyncSession | None = None,
    ) -> BudgetLog:
        """Log a budget check/violation."""
        log_entry = BudgetLog(
            id=str(uuid.uuid4()),
            session_id=session_id,
            task_id=task_id,
            agent_id=agent_id,
            budget_type=budget_type,
            current_value=current_value,
            limit_value=limit_value,
            exceeded=exceeded,
        )

        if db:
            db.add(log_entry)
        else:
            async with async_session_factory() as session:
                session.add(log_entry)
                await session.commit()

        return log_entry

    # =========================================================================
    # Query Methods
    # =========================================================================

    @staticmethod
    async def get_tool_logs(
        session_id: str | None = None,
        agent_id: str | None = None,
        tool_name: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 100,
    ) -> list[ToolAuditLog]:
        """Query tool audit logs."""
        async with async_session_factory() as session:
            query = select(ToolAuditLog)

            conditions = []
            if session_id:
                conditions.append(ToolAuditLog.session_id == session_id)
            if agent_id:
                conditions.append(ToolAuditLog.agent_id == agent_id)
            if tool_name:
                conditions.append(ToolAuditLog.tool_name == tool_name)
            if start_time:
                conditions.append(ToolAuditLog.created_at >= start_time)
            if end_time:
                conditions.append(ToolAuditLog.created_at <= end_time)

            if conditions:
                query = query.where(and_(*conditions))

            query = query.order_by(ToolAuditLog.created_at.desc()).limit(limit)

            result = await session.execute(query)
            return list(result.scalars().all())

    @staticmethod
    async def get_file_changes(
        session_id: str | None = None,
        file_path: str | None = None,
        operation: str | None = None,
        blocked_only: bool = False,
        limit: int = 100,
        decompress: bool = True,
    ) -> list[FileChangeLog]:
        """Query file change logs.

        Args:
            session_id: Filter by session
            file_path: Filter by path (substring match)
            operation: Filter by operation type
            blocked_only: Only return blocked operations
            limit: Maximum results
            decompress: Whether to decompress diffs (default True)

        Returns:
            List of FileChangeLog entries
        """
        async with async_session_factory() as session:
            query = select(FileChangeLog)

            conditions = []
            if session_id:
                conditions.append(FileChangeLog.session_id == session_id)
            if file_path:
                conditions.append(FileChangeLog.file_path.like(f"%{file_path}%"))
            if operation:
                conditions.append(FileChangeLog.operation == operation)
            if blocked_only:
                conditions.append(FileChangeLog.blocked == True)

            if conditions:
                query = query.where(and_(*conditions))

            query = query.order_by(FileChangeLog.created_at.desc()).limit(limit)

            result = await session.execute(query)
            logs = list(result.scalars().all())

            # Decompress diffs if requested
            if decompress:
                for log in logs:
                    if log.diff and log.diff.startswith("GZIP:"):
                        log.diff = decompress_diff(log.diff)

            return logs

    @staticmethod
    async def get_budget_violations(
        session_id: str | None = None,
        agent_id: str | None = None,
        limit: int = 100,
    ) -> list[BudgetLog]:
        """Get budget violations."""
        async with async_session_factory() as session:
            query = select(BudgetLog).where(BudgetLog.exceeded == True)

            if session_id:
                query = query.where(BudgetLog.session_id == session_id)
            if agent_id:
                query = query.where(BudgetLog.agent_id == agent_id)

            query = query.order_by(BudgetLog.created_at.desc()).limit(limit)

            result = await session.execute(query)
            return list(result.scalars().all())

    @staticmethod
    async def get_security_events(
        session_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get security-related events (sandbox violations, blocked ops, budget exceeded)."""
        events = []

        async with async_session_factory() as session:
            # Get sandbox violations
            tool_query = select(ToolAuditLog).where(
                ToolAuditLog.sandbox_violation == True
            )
            if session_id:
                tool_query = tool_query.where(ToolAuditLog.session_id == session_id)
            tool_query = tool_query.order_by(ToolAuditLog.created_at.desc()).limit(limit // 3)

            result = await session.execute(tool_query)
            for log in result.scalars().all():
                events.append({
                    "type": "sandbox_violation",
                    "tool": log.tool_name,
                    "action": log.tool_action,
                    "created_at": log.created_at.isoformat(),
                    "agent_id": log.agent_id,
                })

            # Get blocked file operations
            file_query = select(FileChangeLog).where(FileChangeLog.blocked == True)
            if session_id:
                file_query = file_query.where(FileChangeLog.session_id == session_id)
            file_query = file_query.order_by(FileChangeLog.created_at.desc()).limit(limit // 3)

            result = await session.execute(file_query)
            for log in result.scalars().all():
                events.append({
                    "type": "blocked_file_op",
                    "file_path": log.file_path,
                    "operation": log.operation,
                    "created_at": log.created_at.isoformat(),
                    "agent_id": log.agent_id,
                })

            # Get budget violations
            budget_query = select(BudgetLog).where(BudgetLog.exceeded == True)
            if session_id:
                budget_query = budget_query.where(BudgetLog.session_id == session_id)
            budget_query = budget_query.order_by(BudgetLog.created_at.desc()).limit(limit // 3)

            result = await session.execute(budget_query)
            for log in result.scalars().all():
                events.append({
                    "type": "budget_exceeded",
                    "budget_type": log.budget_type,
                    "current": log.current_value,
                    "limit": log.limit_value,
                    "created_at": log.created_at.isoformat(),
                    "agent_id": log.agent_id,
                })

        # Sort by created_at and limit
        events.sort(key=lambda x: x["created_at"], reverse=True)
        return events[:limit]
