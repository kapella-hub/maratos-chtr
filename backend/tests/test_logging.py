"""Tests for logging configuration."""

import json
import logging

import pytest

from app.logging_config import JSONFormatter, ConsoleFormatter, setup_logging


class TestJSONFormatter:
    """Tests for JSON log formatter."""

    def test_basic_format(self):
        """Test basic JSON log format."""
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        output = formatter.format(record)
        data = json.loads(output)

        assert data["level"] == "INFO"
        assert data["logger"] == "test"
        assert data["message"] == "Test message"
        assert "timestamp" in data

    def test_extra_fields(self):
        """Test extra fields are included."""
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Request",
            args=(),
            exc_info=None,
        )
        record.method = "GET"
        record.path = "/api/chat"
        record.status_code = 200
        record.duration_ms = 150.5

        output = formatter.format(record)
        data = json.loads(output)

        assert data["method"] == "GET"
        assert data["path"] == "/api/chat"
        assert data["status_code"] == 200
        assert data["duration_ms"] == 150.5


class TestConsoleFormatter:
    """Tests for console log formatter."""

    def test_basic_format(self):
        """Test basic console format includes level and message."""
        formatter = ConsoleFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        output = formatter.format(record)

        assert "INFO" in output
        assert "Test message" in output
        assert "test" in output

    def test_extra_fields_in_brackets(self):
        """Test extra fields appear in brackets."""
        formatter = ConsoleFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Request",
            args=(),
            exc_info=None,
        )
        record.method = "GET"
        record.path = "/api/chat"

        output = formatter.format(record)

        assert "GET /api/chat" in output
        assert "[" in output


class TestSetupLogging:
    """Tests for logging setup."""

    def test_setup_creates_handler(self):
        """Test setup_logging creates a handler."""
        # Get initial handler count
        root = logging.getLogger()
        initial_handlers = len(root.handlers)

        setup_logging(debug=True, json_logs=False)

        # Should have replaced/added handler
        assert len(root.handlers) >= 1

    def test_debug_mode_sets_debug_level(self):
        """Test debug mode sets DEBUG level."""
        setup_logging(debug=True, json_logs=False)
        root = logging.getLogger()
        assert root.level == logging.DEBUG

    def test_non_debug_sets_info_level(self):
        """Test non-debug mode sets INFO level."""
        setup_logging(debug=False, json_logs=False)
        root = logging.getLogger()
        assert root.level == logging.INFO
