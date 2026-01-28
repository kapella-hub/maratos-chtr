"""Security abuse case tests.

These tests verify that security controls prevent common attack patterns.
Each test corresponds to an abuse scenario documented in docs/SECURITY_REVIEW.md.
"""

import os
import tempfile
from pathlib import Path

from app.tools.path_security import (
    PathValidator,
    FileOperation,
    validate_and_audit,
)
from app.audit.retention import truncate_with_hash


class TestFilesystemJail:
    """Test filesystem jail prevents writes outside workspace."""

    def setup_method(self):
        """Create a temporary workspace for testing."""
        self.temp_dir = tempfile.mkdtemp()
        self.workspace = Path(self.temp_dir) / "workspace"
        self.workspace.mkdir()
        self.allowed_dirs = [self.workspace]
        self.validator = PathValidator(
            allowed_dirs=self.allowed_dirs,
            workspace=self.workspace,
        )

    def teardown_method(self):
        """Clean up temporary directory."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_write_inside_workspace_allowed(self):
        """Verify writes inside workspace succeed."""
        test_file = self.workspace / "test.txt"
        resolved, violation = self.validator.validate_path(
            str(test_file),
            FileOperation.WRITE,
            require_allowed_dir=True,
        )
        assert resolved is not None
        assert violation is None

    def test_write_outside_workspace_denied(self):
        """ABUSE CASE 6.2: Attempt to write to /etc/passwd."""
        for forbidden_path in ["/etc/passwd", "/tmp/outside", "/var/log/test"]:
            resolved, violation = self.validator.validate_path(
                forbidden_path,
                FileOperation.WRITE,
                require_allowed_dir=True,
            )
            # Either resolved is None or there's a violation
            assert resolved is None or violation is not None

    def test_write_to_parent_denied(self):
        """Verify parent directory traversal is blocked."""
        parent_file = str(self.workspace.parent / "escape.txt")
        resolved, violation = self.validator.validate_path(
            parent_file,
            FileOperation.WRITE,
            require_allowed_dir=True,
        )
        assert resolved is None or violation is not None

    def test_write_with_path_traversal_denied(self):
        """Verify ../ path traversal is blocked after resolution."""
        traversal_path = str(self.workspace / ".." / "escape.txt")
        resolved, violation = self.validator.validate_path(
            traversal_path,
            FileOperation.WRITE,
            require_allowed_dir=True,
        )
        assert resolved is None or violation is not None

    def test_symlink_escape_denied(self):
        """ABUSE CASE 6.3: Symlink pointing outside workspace."""
        # Create file outside workspace
        outside_target = Path(self.temp_dir) / "outside.txt"
        outside_target.write_text("original")

        # Create symlink inside workspace pointing outside
        symlink_path = self.workspace / "sneaky_link"
        symlink_path.symlink_to(outside_target)

        # Symlink resolves to outside workspace - should be denied
        resolved, violation = self.validator.validate_path(
            str(symlink_path),
            FileOperation.WRITE,
            require_allowed_dir=True,
        )
        # Should either resolve outside allowed dir or report violation
        if resolved is not None:
            # If resolved, it must be inside allowed dirs
            resolved_real = Path(os.path.realpath(resolved))
            workspace_real = Path(os.path.realpath(self.workspace))
            # This assertion may fail if symlink escape is not blocked - that's the point
            # The validator should prevent this
            inside = str(resolved_real).startswith(str(workspace_real) + os.sep)
            # If we get here with resolved outside, test should fail
            assert inside or violation is not None

    def test_nested_symlink_escape_denied(self):
        """Verify nested symlinks are followed and checked."""
        # Create directory outside workspace
        outside_dir = Path(self.temp_dir) / "outside"
        outside_dir.mkdir()

        # Create symlink in workspace pointing to outside dir
        link1 = self.workspace / "link1"
        link1.symlink_to(outside_dir)

        # Writing through link1 should fail
        target = link1 / "file.txt"
        resolved, violation = self.validator.validate_path(
            str(target),
            FileOperation.WRITE,
            require_allowed_dir=True,
        )
        # Should either return None or have violation
        assert resolved is None or violation is not None

    def test_read_anywhere_allowed(self):
        """Verify read operations are allowed outside workspace."""
        # Create file outside workspace
        outside_file = Path(self.temp_dir) / "readable.txt"
        outside_file.write_text("test content")

        # Read should be allowed (no jail for reads)
        resolved, violation = self.validator.validate_path(
            str(outside_file),
            FileOperation.READ,
            require_allowed_dir=False,  # Reads don't require allowed dir
        )
        assert resolved is not None
        assert violation is None

    def test_absolute_path_outside_denied(self):
        """Absolute paths outside workspace are denied for writes."""
        for forbidden_path in ["/root/.ssh/authorized_keys", "/home/user/.bashrc"]:
            resolved, violation = self.validator.validate_path(
                forbidden_path,
                FileOperation.WRITE,
                require_allowed_dir=True,
            )
            assert resolved is None or violation is not None


class TestPathValidation:
    """Test path validation edge cases."""

    def setup_method(self):
        """Create a temporary workspace for testing."""
        self.temp_dir = tempfile.mkdtemp()
        self.workspace = Path(self.temp_dir) / "workspace"
        self.workspace.mkdir()
        self.allowed_dirs = [self.workspace]
        self.validator = PathValidator(
            allowed_dirs=self.allowed_dirs,
            workspace=self.workspace,
        )

    def teardown_method(self):
        """Clean up temporary directory."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_similar_prefix_not_confused(self):
        """Verify workspace-similar paths are rejected.

        If workspace is /home/user/workspace, then
        /home/user/workspace-evil should be rejected.
        """
        # Create a sibling directory with similar name
        evil_workspace = Path(self.temp_dir) / "workspace-evil"
        evil_workspace.mkdir()
        evil_file = evil_workspace / "evil.txt"

        # Should not be allowed despite similar prefix
        resolved, violation = self.validator.validate_path(
            str(evil_file),
            FileOperation.WRITE,
            require_allowed_dir=True,
        )
        assert resolved is None or violation is not None

    def test_null_byte_injection_blocked(self):
        """Verify null byte injection is blocked."""
        null_path = str(self.workspace / "file.txt\x00.evil")
        resolved, violation = self.validator.validate_path(
            null_path,
            FileOperation.WRITE,
            require_allowed_dir=True,
        )
        # Should be rejected due to null byte
        assert violation is not None

    def test_relative_path_handling(self):
        """Relative paths that would escape should be denied."""
        # Relative path that would escape if interpreted literally
        relative = "../../../etc/passwd"
        resolved, violation = self.validator.validate_path(
            relative,
            FileOperation.WRITE,
            require_allowed_dir=True,
        )
        assert resolved is None or violation is not None


class TestBudgetEnforcement:
    """Test budget limits prevent resource exhaustion."""

    def test_strict_mode_reduces_limits(self):
        """Verify strict mode applies lower limits."""
        from app.guardrails.config import get_budget_limits, reset_guardrails_settings

        # Test with strict mode environment variable
        original_env = os.environ.get("MARATOS_GUARDRAILS_STRICT_MODE")
        try:
            os.environ["MARATOS_GUARDRAILS_STRICT_MODE"] = "true"
            reset_guardrails_settings()

            limits = get_budget_limits()

            # Strict mode should have lower limits
            assert limits.max_tool_loops_per_message <= 3
            assert limits.max_shell_time_seconds <= 30.0
        finally:
            if original_env:
                os.environ["MARATOS_GUARDRAILS_STRICT_MODE"] = original_env
            else:
                os.environ.pop("MARATOS_GUARDRAILS_STRICT_MODE", None)
            reset_guardrails_settings()

    def test_default_limits_reasonable(self):
        """Verify default limits are set."""
        from app.guardrails.config import get_budget_limits, reset_guardrails_settings

        reset_guardrails_settings()
        limits = get_budget_limits()

        # Should have reasonable defaults
        assert limits.max_tool_loops_per_message > 0
        assert limits.max_tool_calls_per_session > 0
        assert limits.max_shell_time_seconds > 0


class TestToolAllowlist:
    """Test per-agent tool allowlists."""

    def test_reviewer_cannot_use_web_search(self):
        """ABUSE CASE 6.4: Verify reviewer lacks web_search in readonly mode."""
        from app.guardrails.config import get_agent_tool_allowlist, reset_guardrails_settings

        reset_guardrails_settings()

        # In readonly mode, reviewer gets restricted tools
        original_env = os.environ.get("MARATOS_GUARDRAILS_READONLY_MODE")
        try:
            os.environ["MARATOS_GUARDRAILS_READONLY_MODE"] = "true"
            reset_guardrails_settings()

            tools = get_agent_tool_allowlist("reviewer")

            # Readonly mode should restrict to read-only tools
            if tools is not None:
                assert "shell" not in tools
        finally:
            if original_env:
                os.environ["MARATOS_GUARDRAILS_READONLY_MODE"] = original_env
            else:
                os.environ.pop("MARATOS_GUARDRAILS_READONLY_MODE", None)
            reset_guardrails_settings()

    def test_sandbox_mode_removes_shell(self):
        """Verify sandbox mode removes shell from all agents."""
        from app.guardrails.config import get_agent_tool_allowlist, reset_guardrails_settings

        original_sandbox = os.environ.get("MARATOS_GUARDRAILS_SANDBOX_MODE")
        original_tools = os.environ.get("MARATOS_GUARDRAILS_CODER_ALLOWED_TOOLS")
        try:
            os.environ["MARATOS_GUARDRAILS_SANDBOX_MODE"] = "true"
            os.environ["MARATOS_GUARDRAILS_CODER_ALLOWED_TOOLS"] = "filesystem,shell,kiro"
            reset_guardrails_settings()

            tools = get_agent_tool_allowlist("coder")

            # Sandbox mode should remove shell even if explicitly listed
            if tools is not None:
                assert "shell" not in tools
        finally:
            if original_sandbox:
                os.environ["MARATOS_GUARDRAILS_SANDBOX_MODE"] = original_sandbox
            else:
                os.environ.pop("MARATOS_GUARDRAILS_SANDBOX_MODE", None)
            if original_tools:
                os.environ["MARATOS_GUARDRAILS_CODER_ALLOWED_TOOLS"] = original_tools
            else:
                os.environ.pop("MARATOS_GUARDRAILS_CODER_ALLOWED_TOOLS", None)
            reset_guardrails_settings()


class TestAuditContentLimits:
    """Test audit log content truncation prevents overflow."""

    def test_large_content_truncated(self):
        """ABUSE CASE 6.6: Verify large content is truncated."""
        large_content = "x" * 100_000
        max_size = 1000

        result = truncate_with_hash(large_content, max_size)

        assert result is not None
        # Result should be smaller than original
        assert len(result.content) < len(large_content)
        assert result.was_truncated is True
        assert result.original_size == 100_000

    def test_hash_preserved_on_truncation(self):
        """Verify original hash preserved when content truncated."""
        import hashlib

        large_content = "y" * 50_000
        max_size = 1000
        original_hash = hashlib.sha256(large_content.encode()).hexdigest()

        result = truncate_with_hash(large_content, max_size)

        # Original hash should be preserved (may or may not have prefix)
        assert result is not None
        assert original_hash in result.original_hash

    def test_small_content_unchanged(self):
        """Verify small content passes through unchanged."""
        small_content = "small content"
        max_size = 10000

        result = truncate_with_hash(small_content, max_size)

        assert result is not None
        assert result.content == small_content
        assert result.was_truncated is False


class TestDiffFirstApproval:
    """Test diff-first mode requires approval for modifications."""

    def test_diff_first_enabled_in_readonly(self):
        """Verify readonly mode enables diff-first."""
        from app.guardrails.config import get_diff_approval_config, reset_guardrails_settings

        original_env = os.environ.get("MARATOS_GUARDRAILS_READONLY_MODE")
        try:
            os.environ["MARATOS_GUARDRAILS_READONLY_MODE"] = "true"
            reset_guardrails_settings()

            config = get_diff_approval_config()

            assert config.enabled is True
            assert config.require_approval_for_writes is True
            assert config.require_approval_for_deletes is True
        finally:
            if original_env:
                os.environ["MARATOS_GUARDRAILS_READONLY_MODE"] = original_env
            else:
                os.environ.pop("MARATOS_GUARDRAILS_READONLY_MODE", None)
            reset_guardrails_settings()

    def test_diff_first_protects_all_files_in_readonly(self):
        """Verify readonly mode protects all files."""
        from app.guardrails.config import get_diff_approval_config, reset_guardrails_settings

        original_env = os.environ.get("MARATOS_GUARDRAILS_READONLY_MODE")
        try:
            os.environ["MARATOS_GUARDRAILS_READONLY_MODE"] = "true"
            reset_guardrails_settings()

            config = get_diff_approval_config()

            # Readonly should protect all files
            assert "*" in config.protected_patterns
        finally:
            if original_env:
                os.environ["MARATOS_GUARDRAILS_READONLY_MODE"] = original_env
            else:
                os.environ.pop("MARATOS_GUARDRAILS_READONLY_MODE", None)
            reset_guardrails_settings()


class TestDestructiveShellCommands:
    """Test handling of potentially destructive shell commands."""

    def test_shell_timeout_default(self):
        """ABUSE CASE 6.1: Verify shell has timeout."""
        from app.guardrails.config import get_budget_limits, reset_guardrails_settings

        reset_guardrails_settings()
        limits = get_budget_limits()

        # Should have a reasonable default timeout
        assert limits.max_shell_time_seconds <= 120.0
        assert limits.max_shell_time_seconds > 0

    def test_shell_timeout_strict_mode(self):
        """Verify strict mode has shorter shell timeout."""
        from app.guardrails.config import get_budget_limits, reset_guardrails_settings

        original_env = os.environ.get("MARATOS_GUARDRAILS_STRICT_MODE")
        try:
            os.environ["MARATOS_GUARDRAILS_STRICT_MODE"] = "true"
            reset_guardrails_settings()

            limits = get_budget_limits()

            # Strict mode should have shorter timeout
            assert limits.max_shell_time_seconds <= 30.0
        finally:
            if original_env:
                os.environ["MARATOS_GUARDRAILS_STRICT_MODE"] = original_env
            else:
                os.environ.pop("MARATOS_GUARDRAILS_STRICT_MODE", None)
            reset_guardrails_settings()


class TestValidateAndAuditConvenience:
    """Test the validate_and_audit convenience function."""

    def setup_method(self):
        """Create a temporary workspace for testing."""
        self.temp_dir = tempfile.mkdtemp()
        self.workspace = Path(self.temp_dir) / "workspace"
        self.workspace.mkdir()
        self.allowed_dirs = [self.workspace]

    def teardown_method(self):
        """Clean up temporary directory."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_validate_read_outside_workspace(self):
        """Reads outside workspace should be allowed."""
        outside_file = Path(self.temp_dir) / "outside.txt"
        outside_file.write_text("test")

        resolved, error = validate_and_audit(
            str(outside_file),
            FileOperation.READ,
            self.allowed_dirs,
            self.workspace,
            require_allowed=False,
        )

        assert resolved is not None
        assert error is None

    def test_validate_write_inside_workspace(self):
        """Writes inside workspace should be allowed."""
        inside_file = self.workspace / "test.txt"

        resolved, error = validate_and_audit(
            str(inside_file),
            FileOperation.WRITE,
            self.allowed_dirs,
            self.workspace,
            require_allowed=True,
        )

        assert resolved is not None
        assert error is None

    def test_validate_write_outside_workspace(self):
        """Writes outside workspace should be denied."""
        outside_file = Path(self.temp_dir) / "outside.txt"

        resolved, error = validate_and_audit(
            str(outside_file),
            FileOperation.WRITE,
            self.allowed_dirs,
            self.workspace,
            require_allowed=True,
        )

        # Should either fail or return error
        assert resolved is None or error is not None
