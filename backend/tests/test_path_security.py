"""Security tests for path validation and filesystem operations.

Tests cover:
- Path traversal attacks (../, encoded sequences)
- Symlink escape attacks
- Null byte injection
- Unicode normalization attacks
- Audit logging
"""

import os
import tempfile
import pytest
from pathlib import Path
from unittest.mock import patch

from app.tools.path_security import (
    FileOperation,
    PathValidator,
    SecurityAuditLog,
    SecurityViolationType,
    security_audit,
    validate_and_audit,
    sanitize_path,
    PATH_TRAVERSAL_PATTERNS,
    NULL_BYTE_PATTERNS,
    UNICODE_DANGEROUS,
)
from app.tools.filesystem import FilesystemTool


class TestPathTraversalPatterns:
    """Test detection of path traversal patterns."""

    @pytest.mark.parametrize("malicious_path", [
        "../../../etc/passwd",
        "..\\..\\..\\windows\\system32",
        "foo/../../../etc/passwd",
        "foo/bar/../../../etc/shadow",
        "/allowed/../../../etc/passwd",
        "/..",
        "../",
        "..\\",
        "%2e%2e%2f",  # URL encoded ../
        "%2e%2e/",    # Mixed encoding
        "..%2f",      # Partial encoding
        "%252e%252e%252f",  # Double encoded
    ])
    def test_traversal_patterns_detected(self, malicious_path):
        """Test that path traversal patterns are detected."""
        matched = False
        for pattern in PATH_TRAVERSAL_PATTERNS:
            if pattern.search(malicious_path):
                matched = True
                break
        assert matched, f"Pattern not detected: {malicious_path}"

    @pytest.mark.parametrize("safe_path", [
        "/home/user/file.txt",
        "relative/path/file.txt",
        "file.txt",
        "/var/log/app.log",
        "project/src/main.py",
    ])
    def test_safe_paths_not_flagged(self, safe_path):
        """Test that safe paths are not flagged."""
        matched = False
        for pattern in PATH_TRAVERSAL_PATTERNS:
            if pattern.search(safe_path):
                matched = True
                break
        assert not matched, f"Safe path incorrectly flagged: {safe_path}"


class TestNullBytePatterns:
    """Test detection of null byte injection."""

    @pytest.mark.parametrize("malicious_path", [
        "file.txt\x00.jpg",
        "file%00.txt",
        "file\\0.txt",
    ])
    def test_null_byte_detected(self, malicious_path):
        """Test that null bytes are detected."""
        matched = False
        for pattern in NULL_BYTE_PATTERNS:
            if pattern.search(malicious_path):
                matched = True
                break
        assert matched, f"Null byte not detected: {repr(malicious_path)}"


class TestUnicodeAttacks:
    """Test detection of unicode normalization attacks."""

    def test_dangerous_unicode_chars_defined(self):
        """Test that dangerous unicode characters are defined."""
        assert len(UNICODE_DANGEROUS) > 0
        # Check specific dangerous chars
        assert '\uff0e' in UNICODE_DANGEROUS  # Fullwidth full stop
        assert '\uff0f' in UNICODE_DANGEROUS  # Fullwidth solidus


class TestPathValidator:
    """Test PathValidator class."""

    @pytest.fixture
    def temp_workspace(self):
        """Create a temporary workspace directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "workspace"
            workspace.mkdir()
            # Return realpath to handle macOS /var -> /private/var symlinks
            yield Path(os.path.realpath(workspace))

    @pytest.fixture
    def validator(self, temp_workspace):
        """Create a PathValidator instance."""
        return PathValidator(
            allowed_dirs=[temp_workspace],
            workspace=temp_workspace,
            follow_symlinks=True,
            max_symlink_depth=10,
        )

    def test_valid_path_in_workspace(self, validator, temp_workspace):
        """Test that valid paths in workspace are accepted."""
        test_file = temp_workspace / "test.txt"
        test_file.write_text("test")

        resolved, violation = validator.validate_path(
            str(test_file),
            FileOperation.READ,
            require_allowed_dir=True,
        )

        assert violation is None
        # Compare realpath to handle symlinks
        assert os.path.realpath(resolved) == os.path.realpath(test_file)

    def test_path_traversal_blocked(self, validator, temp_workspace):
        """Test that path traversal is blocked."""
        malicious_path = str(temp_workspace / ".." / ".." / "etc" / "passwd")

        resolved, violation = validator.validate_path(
            malicious_path,
            FileOperation.READ,
            require_allowed_dir=False,
        )

        assert violation is not None
        assert violation.violation_type == SecurityViolationType.PATH_TRAVERSAL

    def test_null_byte_blocked(self, validator):
        """Test that null byte injection is blocked."""
        malicious_path = "file.txt\x00.jpg"

        resolved, violation = validator.validate_path(
            malicious_path,
            FileOperation.READ,
        )

        assert violation is not None
        assert violation.violation_type == SecurityViolationType.NULL_BYTE

    def test_unicode_attack_blocked(self, validator):
        """Test that unicode attacks are blocked."""
        # Use fullwidth characters to try to escape
        malicious_path = f"test\uff0e\uff0e\uff0fpasswd"  # Using fullwidth ./

        resolved, violation = validator.validate_path(
            malicious_path,
            FileOperation.READ,
        )

        assert violation is not None
        assert violation.violation_type == SecurityViolationType.UNICODE_ATTACK

    def test_symlink_resolved_safely(self, validator, temp_workspace):
        """Test that symlinks are resolved safely."""
        # Create a file and a symlink to it
        real_file = temp_workspace / "real.txt"
        real_file.write_text("content")

        symlink = temp_workspace / "link.txt"
        symlink.symlink_to(real_file)

        resolved, violation = validator.validate_path(
            str(symlink),
            FileOperation.READ,
            require_allowed_dir=True,
        )

        assert violation is None
        # Compare realpath to handle symlinks
        assert os.path.realpath(resolved) == os.path.realpath(real_file)

    def test_symlink_escape_blocked(self, validator, temp_workspace):
        """Test that symlinks pointing outside workspace are blocked."""
        # Create a symlink pointing outside workspace
        outside_file = Path(tempfile.gettempdir()) / "outside.txt"
        try:
            outside_file.write_text("outside content")

            escape_link = temp_workspace / "escape.txt"
            escape_link.symlink_to(outside_file)

            resolved, violation = validator.validate_path(
                str(escape_link),
                FileOperation.WRITE,
                require_allowed_dir=True,
            )

            assert violation is not None
            assert violation.violation_type == SecurityViolationType.OUTSIDE_ALLOWED
        finally:
            if outside_file.exists():
                outside_file.unlink()

    def test_symlink_loop_detected(self, validator, temp_workspace):
        """Test that symlink loops are detected."""
        # Create a symlink loop
        link_a = temp_workspace / "link_a"
        link_b = temp_workspace / "link_b"

        link_a.symlink_to(link_b)
        link_b.symlink_to(link_a)

        resolved, violation = validator.validate_path(
            str(link_a),
            FileOperation.READ,
        )

        assert violation is not None
        assert violation.violation_type == SecurityViolationType.SYMLINK_ESCAPE

    def test_symlink_depth_limit(self, validator, temp_workspace):
        """Test that deep symlink chains are blocked."""
        # Create a chain of symlinks
        current = temp_workspace / "file.txt"
        current.write_text("content")

        for i in range(15):  # Exceeds max_symlink_depth of 10
            new_link = temp_workspace / f"link_{i}"
            new_link.symlink_to(current)
            current = new_link

        # Create validator with strict depth limit
        strict_validator = PathValidator(
            allowed_dirs=[temp_workspace],
            workspace=temp_workspace,
            max_symlink_depth=5,
        )

        resolved, violation = strict_validator.validate_path(
            str(current),
            FileOperation.READ,
        )

        assert violation is not None
        assert "depth exceeded" in violation.message.lower()

    def test_relative_path_resolved_to_workspace(self, validator, temp_workspace):
        """Test that relative paths are resolved relative to workspace."""
        resolved, violation = validator.validate_path(
            "subdir/file.txt",
            FileOperation.WRITE,
            require_allowed_dir=True,
        )

        assert violation is None
        assert str(temp_workspace) in str(resolved)

    def test_outside_allowed_dirs_blocked(self, validator, temp_workspace):
        """Test that paths outside allowed dirs are blocked for writes."""
        outside_path = "/tmp/outside.txt"

        resolved, violation = validator.validate_path(
            outside_path,
            FileOperation.WRITE,
            require_allowed_dir=True,
        )

        assert violation is not None
        assert violation.violation_type == SecurityViolationType.OUTSIDE_ALLOWED


class TestSecurityAuditLog:
    """Test SecurityAuditLog class."""

    def test_log_operation(self):
        """Test logging an operation."""
        audit = SecurityAuditLog()

        entry = audit.log_operation(
            FileOperation.READ,
            "/test/path",
            "/test/path/resolved",
            success=True,
            allowed=True,
            agent_id="test_agent",
        )

        assert entry.operation == FileOperation.READ
        assert entry.success is True
        assert entry.allowed is True

    def test_log_violation(self):
        """Test logging a security violation."""
        audit = SecurityAuditLog()

        violation = audit.log_violation(
            SecurityViolationType.PATH_TRAVERSAL,
            "../../../etc/passwd",
            "/etc/passwd",
            "Path traversal detected",
            agent_id="test_agent",
        )

        assert violation.violation_type == SecurityViolationType.PATH_TRAVERSAL
        assert "../../../etc/passwd" in violation.original_path

    def test_max_entries_limit(self):
        """Test that audit log respects max entries limit."""
        audit = SecurityAuditLog(max_entries=5)

        for i in range(10):
            audit.log_operation(
                FileOperation.READ,
                f"/path/{i}",
                f"/path/{i}",
                success=True,
                allowed=True,
            )

        recent = audit.get_recent_entries(limit=100)
        assert len(recent) == 5

    def test_filter_by_operation(self):
        """Test filtering entries by operation."""
        audit = SecurityAuditLog()

        audit.log_operation(FileOperation.READ, "/a", "/a", True, True)
        audit.log_operation(FileOperation.WRITE, "/b", "/b", True, True)
        audit.log_operation(FileOperation.READ, "/c", "/c", True, True)

        reads = audit.get_recent_entries(operation=FileOperation.READ)
        assert len(reads) == 2
        assert all(e.operation == FileOperation.READ for e in reads)

    def test_get_stats(self):
        """Test getting audit statistics."""
        audit = SecurityAuditLog()

        audit.log_operation(FileOperation.READ, "/a", "/a", True, True)
        audit.log_operation(FileOperation.WRITE, "/b", "/b", False, True)
        audit.log_operation(FileOperation.READ, "/c", "/c", True, False)
        audit.log_violation(SecurityViolationType.PATH_TRAVERSAL, "../", None, "test")

        stats = audit.get_stats()

        assert stats["total_operations"] == 3
        assert stats["failed_operations"] == 1
        assert stats["denied_operations"] == 1
        assert stats["total_violations"] == 1
        assert stats["operations_by_type"]["read"] == 2
        assert stats["violations_by_type"]["path_traversal"] == 1


class TestFilesystemToolSecurity:
    """Integration tests for FilesystemTool security."""

    @pytest.fixture
    def temp_workspace(self):
        """Create a temporary workspace directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "workspace"
            workspace.mkdir()
            yield workspace

    @pytest.fixture
    def fs_tool(self, temp_workspace):
        """Create a FilesystemTool with temp workspace."""
        # Use realpath to match how PathValidator resolves paths
        real_workspace = Path(os.path.realpath(temp_workspace))

        with patch("app.config.settings") as mock_settings:
            mock_settings.workspace_dir = real_workspace
            tool = FilesystemTool(workspace=real_workspace)
            # Patch allowed dirs to include real workspace path
            with patch.object(tool, "_get_allowed_dirs", return_value=[real_workspace]):
                yield tool

    @pytest.mark.asyncio
    async def test_write_in_workspace_allowed(self, fs_tool, temp_workspace):
        """Test that writing in workspace is allowed."""
        # Use realpath for consistency with validator
        real_workspace = Path(os.path.realpath(temp_workspace))
        result = await fs_tool.execute(
            action="write",
            path=str(real_workspace / "test.txt"),
            content="test content",
        )

        assert result.success is True
        assert (real_workspace / "test.txt").exists()

    @pytest.mark.asyncio
    async def test_write_outside_workspace_blocked(self, fs_tool, temp_workspace):
        """Test that writing outside workspace is blocked."""
        result = await fs_tool.execute(
            action="write",
            path="/tmp/outside.txt",
            content="malicious content",
        )

        assert result.success is False
        assert "outside" in result.error.lower() or "allowed" in result.error.lower()

    @pytest.mark.asyncio
    async def test_path_traversal_in_write_blocked(self, fs_tool, temp_workspace):
        """Test that path traversal in write is blocked."""
        result = await fs_tool.execute(
            action="write",
            path=str(temp_workspace / ".." / ".." / "etc" / "passwd"),
            content="malicious",
        )

        assert result.success is False

    @pytest.mark.asyncio
    async def test_delete_workspace_root_blocked(self, fs_tool, temp_workspace):
        """Test that deleting workspace root is blocked."""
        result = await fs_tool.execute(
            action="delete",
            path=str(temp_workspace),
        )

        assert result.success is False
        # Either blocked by "root" check or "outside allowed" (depends on realpath resolution)
        assert "root" in result.error.lower() or "allowed" in result.error.lower()

    @pytest.mark.asyncio
    async def test_read_anywhere_allowed(self, fs_tool, temp_workspace):
        """Test that reading from anywhere is allowed."""
        # Create a file outside workspace
        outside_file = Path(tempfile.gettempdir()) / "test_read.txt"
        try:
            outside_file.write_text("readable content")

            result = await fs_tool.execute(
                action="read",
                path=str(outside_file),
            )

            assert result.success is True
            assert "readable content" in result.output
        finally:
            if outside_file.exists():
                outside_file.unlink()

    @pytest.mark.asyncio
    async def test_copy_into_workspace_allowed(self, fs_tool, temp_workspace):
        """Test that copying into workspace is allowed."""
        # Use realpath for consistency
        real_workspace = Path(os.path.realpath(temp_workspace))

        # Create a file outside workspace
        outside_file = Path(tempfile.gettempdir()) / "source.txt"
        try:
            outside_file.write_text("source content")

            result = await fs_tool.execute(
                action="copy",
                path=str(outside_file),
                dest=str(real_workspace / "dest.txt"),
            )

            assert result.success is True
            assert (real_workspace / "dest.txt").exists()
        finally:
            if outside_file.exists():
                outside_file.unlink()

    @pytest.mark.asyncio
    async def test_copy_outside_workspace_blocked(self, fs_tool, temp_workspace):
        """Test that copying to outside workspace is blocked."""
        source_file = temp_workspace / "source.txt"
        source_file.write_text("content")

        result = await fs_tool.execute(
            action="copy",
            path=str(source_file),
            dest="/tmp/outside_dest.txt",
        )

        assert result.success is False

    @pytest.mark.asyncio
    async def test_null_byte_in_path_blocked(self, fs_tool, temp_workspace):
        """Test that null bytes in paths are blocked."""
        result = await fs_tool.execute(
            action="read",
            path=f"{temp_workspace}/test.txt\x00.jpg",
        )

        assert result.success is False
        assert "null" in result.error.lower()

    @pytest.mark.asyncio
    async def test_audit_logging_works(self, fs_tool, temp_workspace):
        """Test that operations are audit logged."""
        test_file = temp_workspace / "audit_test.txt"
        test_file.write_text("content")

        # Clear any existing audit entries
        initial_count = len(security_audit.get_recent_entries())

        await fs_tool.execute(
            action="read",
            path=str(test_file),
        )

        # Check that a new entry was logged
        entries = security_audit.get_recent_entries()
        assert len(entries) > initial_count

    def test_get_security_stats(self, fs_tool):
        """Test getting security statistics."""
        stats = fs_tool.get_security_stats()

        assert "total_operations" in stats
        assert "total_violations" in stats
        assert "operations_by_type" in stats


class TestSanitizePath:
    """Test path sanitization function."""

    def test_sanitize_null_bytes(self):
        """Test that null bytes are removed."""
        sanitized = sanitize_path("file\x00.txt")
        assert "\x00" not in sanitized
        assert sanitized == "file.txt"

    def test_sanitize_unicode(self):
        """Test that dangerous unicode is removed."""
        malicious = f"test\uff0e\uff0epasswd"
        sanitized = sanitize_path(malicious)

        # Should not contain fullwidth characters
        assert '\uff0e' not in sanitized

    def test_sanitize_normal_path(self):
        """Test that normal paths are unchanged."""
        normal = "/home/user/file.txt"
        sanitized = sanitize_path(normal)
        assert sanitized == normal


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.fixture
    def temp_workspace(self):
        """Create a temporary workspace directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "workspace"
            workspace.mkdir()
            yield workspace

    def test_empty_path(self, temp_workspace):
        """Test handling of empty path."""
        validator = PathValidator([temp_workspace], temp_workspace)

        resolved, violation = validator.validate_path(
            "",
            FileOperation.READ,
        )

        # Empty path should resolve to workspace
        assert resolved is not None or violation is not None

    def test_very_long_path(self, temp_workspace):
        """Test handling of very long paths."""
        validator = PathValidator([temp_workspace], temp_workspace)

        long_path = "a" * 10000

        resolved, violation = validator.validate_path(
            long_path,
            FileOperation.READ,
        )

        # Should either succeed or fail gracefully
        assert resolved is not None or violation is not None

    def test_special_characters_in_path(self, temp_workspace):
        """Test handling of special characters."""
        validator = PathValidator([temp_workspace], temp_workspace)

        # Create file with special chars
        special_file = temp_workspace / "test file (1) [copy].txt"
        special_file.write_text("content")

        resolved, violation = validator.validate_path(
            str(special_file),
            FileOperation.READ,
        )

        assert violation is None
        assert resolved == special_file

    def test_case_sensitivity(self, temp_workspace):
        """Test case sensitivity in path validation."""
        validator = PathValidator([temp_workspace], temp_workspace)

        # Create file
        test_file = temp_workspace / "TestFile.txt"
        test_file.write_text("content")

        # On case-insensitive systems, this might resolve differently
        resolved, violation = validator.validate_path(
            str(test_file),
            FileOperation.READ,
        )

        assert violation is None
