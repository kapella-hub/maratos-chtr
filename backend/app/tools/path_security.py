"""Path security validation and audit logging for filesystem operations.

This module provides comprehensive protection against:
- Path traversal attacks (../, encoded sequences)
- Symlink escape attacks
- Race conditions (TOCTOU)
- Null byte injection
- Unicode normalization attacks
"""

import logging
import os
import re
import stat
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Audit logger - separate from general logging
audit_logger = logging.getLogger("maratos.security.audit")


class SecurityViolationType(str, Enum):
    """Types of security violations detected."""
    PATH_TRAVERSAL = "path_traversal"
    SYMLINK_ESCAPE = "symlink_escape"
    NULL_BYTE = "null_byte"
    UNICODE_ATTACK = "unicode_attack"
    OUTSIDE_ALLOWED = "outside_allowed"
    INVALID_PATH = "invalid_path"
    PERMISSION_DENIED = "permission_denied"
    RACE_CONDITION = "race_condition"


class FileOperation(str, Enum):
    """Types of filesystem operations."""
    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    LIST = "list"
    EXISTS = "exists"
    COPY = "copy"
    CREATE_DIR = "create_dir"


@dataclass
class SecurityViolation:
    """Details about a security violation."""
    violation_type: SecurityViolationType
    original_path: str
    resolved_path: str | None
    message: str
    timestamp: datetime = field(default_factory=datetime.now)
    agent_id: str | None = None
    session_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.violation_type.value,
            "original_path": self.original_path,
            "resolved_path": self.resolved_path,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
            "agent_id": self.agent_id,
            "session_id": self.session_id,
        }


@dataclass
class AuditEntry:
    """Audit log entry for filesystem operations."""
    operation: FileOperation
    path: str
    resolved_path: str
    success: bool
    allowed: bool
    timestamp: datetime = field(default_factory=datetime.now)
    agent_id: str | None = None
    session_id: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation": self.operation.value,
            "path": self.path,
            "resolved_path": self.resolved_path,
            "success": self.success,
            "allowed": self.allowed,
            "timestamp": self.timestamp.isoformat(),
            "agent_id": self.agent_id,
            "session_id": self.session_id,
            "details": self.details,
            "error": self.error,
        }


class SecurityAuditLog:
    """Maintains audit log of filesystem operations and security violations."""

    def __init__(self, max_entries: int = 1000, max_violations: int = 500):
        self._entries: list[AuditEntry] = []
        self._violations: list[SecurityViolation] = []
        self._max_entries = max_entries
        self._max_violations = max_violations

    def log_operation(
        self,
        operation: FileOperation,
        path: str,
        resolved_path: str,
        success: bool,
        allowed: bool,
        agent_id: str | None = None,
        session_id: str | None = None,
        details: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> AuditEntry:
        """Log a filesystem operation."""
        entry = AuditEntry(
            operation=operation,
            path=path,
            resolved_path=resolved_path,
            success=success,
            allowed=allowed,
            agent_id=agent_id,
            session_id=session_id,
            details=details or {},
            error=error,
        )

        self._entries.append(entry)
        if len(self._entries) > self._max_entries:
            self._entries = self._entries[-self._max_entries:]

        # Log to audit logger
        log_level = logging.INFO if success and allowed else logging.WARNING
        audit_logger.log(
            log_level,
            f"FS {operation.value.upper()}: {path} -> {resolved_path} "
            f"[{'OK' if success else 'FAIL'}] [{'ALLOWED' if allowed else 'DENIED'}]"
            f"{f' agent={agent_id}' if agent_id else ''}"
            f"{f' error={error}' if error else ''}"
        )

        return entry

    def log_violation(
        self,
        violation_type: SecurityViolationType,
        original_path: str,
        resolved_path: str | None,
        message: str,
        agent_id: str | None = None,
        session_id: str | None = None,
    ) -> SecurityViolation:
        """Log a security violation."""
        violation = SecurityViolation(
            violation_type=violation_type,
            original_path=original_path,
            resolved_path=resolved_path,
            message=message,
            agent_id=agent_id,
            session_id=session_id,
        )

        self._violations.append(violation)
        if len(self._violations) > self._max_violations:
            self._violations = self._violations[-self._max_violations:]

        # Log as warning/error to audit logger
        audit_logger.warning(
            f"SECURITY VIOLATION [{violation_type.value}]: {message} "
            f"path={original_path} resolved={resolved_path}"
            f"{f' agent={agent_id}' if agent_id else ''}"
        )

        # Also log to standard logger for visibility
        logger.warning(f"Security violation: {violation_type.value} - {message}")

        return violation

    def get_recent_entries(
        self,
        limit: int = 100,
        operation: FileOperation | None = None,
        success: bool | None = None,
    ) -> list[AuditEntry]:
        """Get recent audit entries with optional filters."""
        entries = self._entries

        if operation is not None:
            entries = [e for e in entries if e.operation == operation]
        if success is not None:
            entries = [e for e in entries if e.success == success]

        return entries[-limit:]

    def get_recent_violations(
        self,
        limit: int = 100,
        violation_type: SecurityViolationType | None = None,
    ) -> list[SecurityViolation]:
        """Get recent security violations with optional filter."""
        violations = self._violations

        if violation_type is not None:
            violations = [v for v in violations if v.violation_type == violation_type]

        return violations[-limit:]

    def get_stats(self) -> dict[str, Any]:
        """Get audit statistics."""
        total_ops = len(self._entries)
        failed_ops = sum(1 for e in self._entries if not e.success)
        denied_ops = sum(1 for e in self._entries if not e.allowed)

        ops_by_type = {}
        for entry in self._entries:
            ops_by_type[entry.operation.value] = ops_by_type.get(entry.operation.value, 0) + 1

        violations_by_type = {}
        for violation in self._violations:
            violations_by_type[violation.violation_type.value] = (
                violations_by_type.get(violation.violation_type.value, 0) + 1
            )

        return {
            "total_operations": total_ops,
            "failed_operations": failed_ops,
            "denied_operations": denied_ops,
            "total_violations": len(self._violations),
            "operations_by_type": ops_by_type,
            "violations_by_type": violations_by_type,
        }


# Global audit log
security_audit = SecurityAuditLog()


# Dangerous patterns to detect
PATH_TRAVERSAL_PATTERNS = [
    re.compile(r'\.\.[\\/]'),  # ../  or ..\
    re.compile(r'[\\/]\.\.'),  # /../ or \..
    re.compile(r'^\.\.'),      # starts with ..
    re.compile(r'%2e%2e', re.IGNORECASE),  # URL encoded ..
    re.compile(r'%252e%252e', re.IGNORECASE),  # Double URL encoded
    re.compile(r'\.%2e', re.IGNORECASE),  # .%2e
    re.compile(r'%2e\.', re.IGNORECASE),  # %2e.
]

# Null byte patterns
NULL_BYTE_PATTERNS = [
    re.compile(r'\x00'),       # Literal null byte
    re.compile(r'%00'),        # URL encoded null
    re.compile(r'\\0'),        # Escaped null
]

# Unicode normalization attack patterns
UNICODE_DANGEROUS = [
    '\u2024',  # ONE DOT LEADER (looks like .)
    '\u2025',  # TWO DOT LEADER
    '\u2026',  # HORIZONTAL ELLIPSIS
    '\uff0e',  # FULLWIDTH FULL STOP (looks like .)
    '\uff0f',  # FULLWIDTH SOLIDUS (looks like /)
    '\uff3c',  # FULLWIDTH REVERSE SOLIDUS (looks like \)
]


class PathValidator:
    """Validates paths for security before filesystem operations."""

    def __init__(
        self,
        allowed_dirs: list[Path],
        workspace: Path,
        follow_symlinks: bool = True,
        max_symlink_depth: int = 10,
    ):
        # Use realpath to fully resolve all symlinks (handles macOS /var -> /private/var)
        self.allowed_dirs = [Path(os.path.realpath(d)) for d in allowed_dirs]
        self.workspace = Path(os.path.realpath(workspace))
        self.follow_symlinks = follow_symlinks
        self.max_symlink_depth = max_symlink_depth

    def validate_path(
        self,
        path_str: str,
        operation: FileOperation,
        require_allowed_dir: bool = False,
        agent_id: str | None = None,
        session_id: str | None = None,
    ) -> tuple[Path | None, SecurityViolation | None]:
        """Validate a path for the given operation.

        Args:
            path_str: The path string to validate
            operation: The intended operation
            require_allowed_dir: Whether the path must be in allowed dirs
            agent_id: Optional agent ID for logging
            session_id: Optional session ID for logging

        Returns:
            Tuple of (resolved_path, violation) - violation is None if path is safe
        """
        # Check for null bytes
        violation = self._check_null_bytes(path_str, agent_id, session_id)
        if violation:
            return None, violation

        # Check for unicode attacks
        violation = self._check_unicode_attacks(path_str, agent_id, session_id)
        if violation:
            return None, violation

        # Check for path traversal patterns in raw string
        violation = self._check_traversal_patterns(path_str, agent_id, session_id)
        if violation:
            return None, violation

        # Expand and resolve path
        try:
            path = Path(path_str).expanduser()
            if not path.is_absolute():
                path = self.workspace / path

            # Resolve symlinks safely
            resolved, violation = self._safe_resolve(path, agent_id, session_id)
            if violation:
                return None, violation

        except (OSError, ValueError) as e:
            violation = security_audit.log_violation(
                SecurityViolationType.INVALID_PATH,
                path_str,
                None,
                f"Invalid path: {e}",
                agent_id,
                session_id,
            )
            return None, violation

        # Check if resolved path is within allowed directories (for write operations)
        if require_allowed_dir:
            if not self._is_within_allowed(resolved):
                violation = security_audit.log_violation(
                    SecurityViolationType.OUTSIDE_ALLOWED,
                    path_str,
                    str(resolved),
                    f"Path {resolved} is outside allowed directories",
                    agent_id,
                    session_id,
                )
                return None, violation

        # Final safety check - ensure no path traversal after resolution
        violation = self._verify_no_escape(path_str, resolved, require_allowed_dir, agent_id, session_id)
        if violation:
            return None, violation

        return resolved, None

    def _check_null_bytes(
        self,
        path_str: str,
        agent_id: str | None,
        session_id: str | None,
    ) -> SecurityViolation | None:
        """Check for null byte injection attacks."""
        for pattern in NULL_BYTE_PATTERNS:
            if pattern.search(path_str):
                return security_audit.log_violation(
                    SecurityViolationType.NULL_BYTE,
                    path_str,
                    None,
                    "Null byte detected in path",
                    agent_id,
                    session_id,
                )
        return None

    def _check_unicode_attacks(
        self,
        path_str: str,
        agent_id: str | None,
        session_id: str | None,
    ) -> SecurityViolation | None:
        """Check for unicode normalization attacks."""
        # Normalize to NFKC and compare
        normalized = unicodedata.normalize('NFKC', path_str)
        if normalized != path_str:
            # Check if normalization reveals dangerous characters
            for char in UNICODE_DANGEROUS:
                if char in path_str:
                    return security_audit.log_violation(
                        SecurityViolationType.UNICODE_ATTACK,
                        path_str,
                        None,
                        f"Suspicious unicode character detected: U+{ord(char):04X}",
                        agent_id,
                        session_id,
                    )

        return None

    def _check_traversal_patterns(
        self,
        path_str: str,
        agent_id: str | None,
        session_id: str | None,
    ) -> SecurityViolation | None:
        """Check for path traversal patterns."""
        for pattern in PATH_TRAVERSAL_PATTERNS:
            if pattern.search(path_str):
                return security_audit.log_violation(
                    SecurityViolationType.PATH_TRAVERSAL,
                    path_str,
                    None,
                    f"Path traversal pattern detected: {pattern.pattern}",
                    agent_id,
                    session_id,
                )
        return None

    def _safe_resolve(
        self,
        path: Path,
        agent_id: str | None,
        session_id: str | None,
    ) -> tuple[Path | None, SecurityViolation | None]:
        """Safely resolve a path, following symlinks with depth limit."""
        if not self.follow_symlinks:
            # Don't follow symlinks - use strict=False to handle non-existent paths
            try:
                # Get the absolute path without following symlinks
                resolved = Path(os.path.abspath(path))
                return resolved, None
            except (OSError, ValueError) as e:
                violation = security_audit.log_violation(
                    SecurityViolationType.INVALID_PATH,
                    str(path),
                    None,
                    f"Could not resolve path: {e}",
                    agent_id,
                    session_id,
                )
                return None, violation

        # Follow symlinks with depth limit
        current = path
        depth = 0
        visited = set()

        while depth < self.max_symlink_depth:
            try:
                # Get absolute path
                current = Path(os.path.abspath(current))

                # Check if it's a symlink
                if current.is_symlink():
                    # Detect symlink loops
                    current_str = str(current)
                    if current_str in visited:
                        violation = security_audit.log_violation(
                            SecurityViolationType.SYMLINK_ESCAPE,
                            str(path),
                            current_str,
                            "Symlink loop detected",
                            agent_id,
                            session_id,
                        )
                        return None, violation

                    visited.add(current_str)

                    # Read symlink target
                    target = os.readlink(current)
                    if not os.path.isabs(target):
                        target = os.path.join(os.path.dirname(current), target)

                    current = Path(target)
                    depth += 1
                else:
                    # Not a symlink, we're done
                    return current, None

            except (OSError, ValueError) as e:
                violation = security_audit.log_violation(
                    SecurityViolationType.INVALID_PATH,
                    str(path),
                    str(current) if current else None,
                    f"Error resolving symlink: {e}",
                    agent_id,
                    session_id,
                )
                return None, violation

        # Max depth exceeded
        violation = security_audit.log_violation(
            SecurityViolationType.SYMLINK_ESCAPE,
            str(path),
            str(current),
            f"Symlink depth exceeded ({self.max_symlink_depth})",
            agent_id,
            session_id,
        )
        return None, violation

    def _is_within_allowed(self, resolved: Path) -> bool:
        """Check if resolved path is within any allowed directory."""
        # Fully resolve the path (following all symlinks)
        try:
            resolved_real = Path(os.path.realpath(resolved))
        except (OSError, ValueError):
            resolved_real = resolved

        resolved_str = str(resolved_real)

        for allowed_dir in self.allowed_dirs:
            # Fully resolve allowed dir as well
            try:
                allowed_real = Path(os.path.realpath(allowed_dir))
            except (OSError, ValueError):
                allowed_real = allowed_dir

            allowed_str = str(allowed_real)

            # Check if path starts with allowed dir (with proper separator)
            if resolved_str == allowed_str:
                return True
            if resolved_str.startswith(allowed_str + os.sep):
                return True

        return False

    def _verify_no_escape(
        self,
        original: str,
        resolved: Path,
        require_allowed: bool,
        agent_id: str | None,
        session_id: str | None,
    ) -> SecurityViolation | None:
        """Verify the resolved path hasn't escaped expected boundaries."""
        # For relative paths that started in workspace, verify they're still there
        original_path = Path(original).expanduser()

        if not original_path.is_absolute():
            # Was relative to workspace - must still be in allowed dirs after resolution
            if require_allowed and not self._is_within_allowed(resolved):
                return security_audit.log_violation(
                    SecurityViolationType.PATH_TRAVERSAL,
                    original,
                    str(resolved),
                    "Relative path escaped to outside allowed directories",
                    agent_id,
                    session_id,
                )

        return None


def validate_and_audit(
    path_str: str,
    operation: FileOperation,
    allowed_dirs: list[Path],
    workspace: Path,
    require_allowed: bool = False,
    agent_id: str | None = None,
    session_id: str | None = None,
) -> tuple[Path | None, str | None]:
    """Convenience function to validate path and log audit entry.

    Args:
        path_str: Path to validate
        operation: The operation being performed
        allowed_dirs: List of allowed write directories
        workspace: Workspace directory
        require_allowed: Whether path must be in allowed dirs
        agent_id: Optional agent ID
        session_id: Optional session ID

    Returns:
        Tuple of (resolved_path, error_message)
    """
    validator = PathValidator(allowed_dirs, workspace)

    resolved, violation = validator.validate_path(
        path_str,
        operation,
        require_allowed,
        agent_id,
        session_id,
    )

    if violation:
        security_audit.log_operation(
            operation,
            path_str,
            violation.resolved_path or "N/A",
            success=False,
            allowed=False,
            agent_id=agent_id,
            session_id=session_id,
            error=violation.message,
        )
        return None, violation.message

    # Log successful validation
    security_audit.log_operation(
        operation,
        path_str,
        str(resolved),
        success=True,
        allowed=True,
        agent_id=agent_id,
        session_id=session_id,
    )

    return resolved, None


def sanitize_path(path_str: str) -> str:
    """Sanitize a path string by removing dangerous characters.

    Note: This is a last-resort sanitization. Prefer rejection over sanitization.
    """
    # Normalize unicode
    sanitized = unicodedata.normalize('NFKC', path_str)

    # Remove null bytes
    sanitized = sanitized.replace('\x00', '')

    # Remove dangerous unicode characters
    for char in UNICODE_DANGEROUS:
        sanitized = sanitized.replace(char, '')

    return sanitized
