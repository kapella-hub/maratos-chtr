"""Audit logger with file and database backends."""

import asyncio
import json
import logging
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any

from app.audit.models import (
    AuditEvent,
    AuditCategory,
    AuditSeverity,
    ChatAuditEvent,
    AgentAuditEvent,
    ToolAuditEvent,
    FileAuditEvent,
)

logger = logging.getLogger(__name__)


class AuditLogger:
    """Centralized audit logging with multiple backends.

    Supports:
    - File-based logging (JSON lines format)
    - In-memory buffer for recent events
    - Database persistence (optional)
    - Async write to avoid blocking
    """

    def __init__(
        self,
        log_dir: Path | None = None,
        buffer_size: int = 1000,
        flush_interval: float = 5.0,
    ):
        self._log_dir = log_dir or Path.home() / ".maratos" / "audit"
        self._log_dir.mkdir(parents=True, exist_ok=True)

        self._buffer: deque[AuditEvent] = deque(maxlen=buffer_size)
        self._write_buffer: list[AuditEvent] = []
        self._flush_interval = flush_interval
        self._flush_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()
        self._started = False

    async def start(self) -> None:
        """Start the audit logger background tasks."""
        if self._started:
            return
        self._started = True
        self._flush_task = asyncio.create_task(self._flush_loop())
        logger.info(f"Audit logger started, writing to {self._log_dir}")

    async def stop(self) -> None:
        """Stop the audit logger and flush remaining events."""
        if not self._started:
            return
        self._started = False
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
        await self._flush_to_file()
        logger.info("Audit logger stopped")

    async def _flush_loop(self) -> None:
        """Background task to periodically flush events to file."""
        while self._started:
            try:
                await asyncio.sleep(self._flush_interval)
                await self._flush_to_file()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in audit flush loop: {e}")

    async def _flush_to_file(self) -> None:
        """Write buffered events to log file."""
        async with self._lock:
            if not self._write_buffer:
                return

            events = self._write_buffer.copy()
            self._write_buffer.clear()

        # Write to daily log file
        today = datetime.utcnow().strftime("%Y-%m-%d")
        log_file = self._log_dir / f"audit-{today}.jsonl"

        try:
            with open(log_file, "a") as f:
                for event in events:
                    f.write(event.to_json() + "\n")
        except Exception as e:
            logger.error(f"Failed to write audit log: {e}")
            # Re-add events to buffer
            async with self._lock:
                self._write_buffer.extend(events)

    def log(self, event: AuditEvent) -> None:
        """Log an audit event (synchronous, non-blocking)."""
        self._buffer.append(event)
        self._write_buffer.append(event)

        # Also log to standard logger for immediate visibility
        log_msg = f"[AUDIT:{event.category.value}] {event.action}"
        if event.session_id:
            log_msg += f" session={event.session_id[:8]}"
        if event.agent_id:
            log_msg += f" agent={event.agent_id}"
        if event.task_id:
            log_msg += f" task={event.task_id[:8]}"
        if not event.success:
            log_msg += f" ERROR: {event.error}"

        if event.severity == AuditSeverity.ERROR:
            logger.error(log_msg)
        elif event.severity == AuditSeverity.WARNING:
            logger.warning(log_msg)
        else:
            logger.info(log_msg)

    def log_chat_request(
        self,
        session_id: str,
        message: str,
        agent_id: str,
        model: str | None = None,
    ) -> ChatAuditEvent:
        """Log a chat request."""
        event = ChatAuditEvent(
            action="chat_request",
            session_id=session_id,
            agent_id=agent_id,
            message_hash=ChatAuditEvent.hash_content(message),
            message_length=len(message),
            model=model,
        )
        self.log(event)
        return event

    def log_chat_response(
        self,
        session_id: str,
        agent_id: str,
        response_length: int,
        duration_ms: float,
        success: bool = True,
        error: str | None = None,
        model: str | None = None,
    ) -> ChatAuditEvent:
        """Log a chat response."""
        event = ChatAuditEvent(
            action="chat_response",
            session_id=session_id,
            agent_id=agent_id,
            response_length=response_length,
            duration_ms=duration_ms,
            success=success,
            error=error,
            model=model,
            severity=AuditSeverity.ERROR if not success else AuditSeverity.INFO,
        )
        self.log(event)
        return event

    def log_agent_spawn(
        self,
        session_id: str,
        task_id: str,
        agent_id: str,
        spawn_reason: str,
        parent_task_id: str | None = None,
    ) -> AgentAuditEvent:
        """Log an agent spawn."""
        event = AgentAuditEvent(
            action="agent_spawn",
            session_id=session_id,
            task_id=task_id,
            agent_id=agent_id,
            parent_task_id=parent_task_id,
            spawn_reason=spawn_reason[:200],  # Truncate
        )
        self.log(event)
        return event

    def log_agent_complete(
        self,
        session_id: str,
        task_id: str,
        agent_id: str,
        duration_ms: float,
        success: bool,
        goals_total: int = 0,
        goals_completed: int = 0,
        goals_failed: int = 0,
        error: str | None = None,
    ) -> AgentAuditEvent:
        """Log agent completion."""
        event = AgentAuditEvent(
            action="agent_complete",
            session_id=session_id,
            task_id=task_id,
            agent_id=agent_id,
            duration_ms=duration_ms,
            success=success,
            error=error,
            goals_total=goals_total,
            goals_completed=goals_completed,
            goals_failed=goals_failed,
            severity=AuditSeverity.ERROR if not success else AuditSeverity.INFO,
        )
        self.log(event)
        return event

    def log_tool_call(
        self,
        session_id: str | None,
        task_id: str | None,
        tool_name: str,
        tool_action: str | None,
        parameters: dict[str, Any],
        agent_id: str | None = None,
    ) -> ToolAuditEvent:
        """Log a tool call (before execution)."""
        event = ToolAuditEvent(
            action="tool_call",
            session_id=session_id,
            task_id=task_id,
            agent_id=agent_id,
            tool_name=tool_name,
            tool_action=tool_action,
            parameters_hash=ToolAuditEvent.hash_params(parameters),
        )
        self.log(event)
        return event

    def log_tool_result(
        self,
        session_id: str | None,
        task_id: str | None,
        tool_name: str,
        success: bool,
        output_length: int,
        duration_ms: float,
        error: str | None = None,
        sandbox_violation: bool = False,
        agent_id: str | None = None,
    ) -> ToolAuditEvent:
        """Log a tool result (after execution)."""
        severity = AuditSeverity.INFO
        if not success:
            severity = AuditSeverity.ERROR
        if sandbox_violation:
            severity = AuditSeverity.CRITICAL

        event = ToolAuditEvent(
            action="tool_result",
            session_id=session_id,
            task_id=task_id,
            agent_id=agent_id,
            tool_name=tool_name,
            success=success,
            output_length=output_length,
            duration_ms=duration_ms,
            error=error,
            sandbox_violation=sandbox_violation,
            severity=severity,
        )
        self.log(event)
        return event

    def log_file_operation(
        self,
        session_id: str | None,
        task_id: str | None,
        file_path: str,
        operation: str,
        success: bool,
        in_workspace: bool,
        blocked: bool = False,
        file_size: int | None = None,
        error: str | None = None,
    ) -> FileAuditEvent:
        """Log a file operation."""
        severity = AuditSeverity.INFO
        if blocked:
            severity = AuditSeverity.WARNING
        if not success:
            severity = AuditSeverity.ERROR

        event = FileAuditEvent(
            action=f"file_{operation}",
            session_id=session_id,
            task_id=task_id,
            file_path=file_path,
            operation=operation,
            success=success,
            in_workspace=in_workspace,
            blocked=blocked,
            file_size=file_size,
            error=error,
            severity=severity,
        )
        self.log(event)
        return event

    def get_recent_events(
        self,
        limit: int = 100,
        category: AuditCategory | None = None,
        session_id: str | None = None,
    ) -> list[AuditEvent]:
        """Get recent events from buffer."""
        events = list(self._buffer)

        if category:
            events = [e for e in events if e.category == category]
        if session_id:
            events = [e for e in events if e.session_id == session_id]

        return events[-limit:]

    async def query_events(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        category: AuditCategory | None = None,
        session_id: str | None = None,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        """Query events from log files."""
        events = []

        # Determine date range
        if not start_date:
            start_date = datetime.utcnow().replace(hour=0, minute=0, second=0)
        if not end_date:
            end_date = datetime.utcnow()

        # Find relevant log files
        current = start_date
        while current <= end_date:
            date_str = current.strftime("%Y-%m-%d")
            log_file = self._log_dir / f"audit-{date_str}.jsonl"

            if log_file.exists():
                try:
                    with open(log_file, "r") as f:
                        for line in f:
                            try:
                                event = json.loads(line)

                                # Filter
                                if category and event.get("category") != category.value:
                                    continue
                                if session_id and event.get("session_id") != session_id:
                                    continue

                                events.append(event)

                                if len(events) >= limit:
                                    return events
                            except json.JSONDecodeError:
                                continue
                except Exception as e:
                    logger.error(f"Error reading audit log {log_file}: {e}")

            current = current.replace(day=current.day + 1)

        return events


# Global audit logger instance
audit_logger = AuditLogger()
