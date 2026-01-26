"""Logging configuration for MaratOS."""

import json
import logging
import sys
from datetime import datetime
from typing import Any


class JSONFormatter(logging.Formatter):
    """JSON log formatter for structured logging in production."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_data: dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add extra fields from record
        if hasattr(record, "method"):
            log_data["method"] = record.method
        if hasattr(record, "path"):
            log_data["path"] = record.path
        if hasattr(record, "status_code"):
            log_data["status_code"] = record.status_code
        if hasattr(record, "duration_ms"):
            log_data["duration_ms"] = record.duration_ms
        if hasattr(record, "client_ip"):
            log_data["client_ip"] = record.client_ip
        if hasattr(record, "session_id"):
            log_data["session_id"] = record.session_id
        if hasattr(record, "agent_id"):
            log_data["agent_id"] = record.agent_id
        if hasattr(record, "task_id"):
            log_data["task_id"] = record.task_id

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data)


class ConsoleFormatter(logging.Formatter):
    """Colored console formatter for development."""

    COLORS = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        """Format log record with colors."""
        color = self.COLORS.get(record.levelname, "")
        timestamp = datetime.now().strftime("%H:%M:%S")

        # Build extra info string
        extras = []
        if hasattr(record, "method") and hasattr(record, "path"):
            extras.append(f"{record.method} {record.path}")
        if hasattr(record, "status_code"):
            extras.append(f"status={record.status_code}")
        if hasattr(record, "duration_ms"):
            extras.append(f"{record.duration_ms:.1f}ms")
        if hasattr(record, "session_id"):
            extras.append(f"session={record.session_id[:8]}...")
        if hasattr(record, "agent_id"):
            extras.append(f"agent={record.agent_id}")

        extra_str = f" [{', '.join(extras)}]" if extras else ""

        message = f"{timestamp} {color}{record.levelname:8}{self.RESET} {record.name}: {record.getMessage()}{extra_str}"

        if record.exc_info:
            message += "\n" + self.formatException(record.exc_info)

        return message


def setup_logging(debug: bool = False, json_logs: bool = False) -> None:
    """Configure application logging.

    Args:
        debug: Enable debug level logging
        json_logs: Use JSON format (for production)
    """
    # Determine log level
    level = logging.DEBUG if debug else logging.INFO

    # Create handler
    handler = logging.StreamHandler(sys.stdout)

    # Set formatter based on mode
    if json_logs and not debug:
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(ConsoleFormatter())

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Remove existing handlers
    for existing_handler in root_logger.handlers[:]:
        root_logger.removeHandler(existing_handler)

    root_logger.addHandler(handler)

    # Reduce noise from third-party libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

    # Log startup message
    logger = logging.getLogger(__name__)
    logger.info(f"Logging configured: level={logging.getLevelName(level)}, json={json_logs}")
