"""Filesystem tools with sandboxed write access and security validation."""

import os
import shutil
from pathlib import Path
from typing import Any

from app.tools.base import Tool, ToolParameter, ToolResult, registry
from app.tools.path_security import (
    FileOperation,
    PathValidator,
    security_audit,
    validate_and_audit,
)


class FilesystemTool(Tool):
    """Tool for filesystem operations with sandboxed writes.

    Security model:
    - READ: Allowed anywhere on the filesystem
    - WRITE: Only allowed in configured allowed directories (workspace + custom dirs)
    - All paths are validated for security (traversal, symlinks, etc.)
    - All operations are audit logged
    - Configure allowed dirs via MARATOS_ALLOWED_WRITE_DIRS env var
    """

    def __init__(self, workspace: Path | None = None) -> None:
        super().__init__(
            id="filesystem",
            name="Filesystem",
            description="Read files anywhere, write only to allowed directories. Configure allowed dirs in settings.",
            parameters=[
                ToolParameter(
                    name="action",
                    type="string",
                    description="Action: read (anywhere), list (anywhere), exists (anywhere), write/delete/copy (allowed dirs only)",
                    enum=["read", "write", "list", "delete", "exists", "copy"],
                ),
                ToolParameter(
                    name="path",
                    type="string",
                    description="File or directory path",
                ),
                ToolParameter(
                    name="content",
                    type="string",
                    description="Content to write (for write action)",
                    required=False,
                ),
                ToolParameter(
                    name="dest",
                    type="string",
                    description="Destination path for copy. Can be in any allowed write directory.",
                    required=False,
                ),
                ToolParameter(
                    name="offset",
                    type="number",
                    description="Line offset for reading (1-indexed)",
                    required=False,
                    default=1,
                ),
                ToolParameter(
                    name="limit",
                    type="number",
                    description="Max lines to read",
                    required=False,
                    default=500,
                ),
            ],
        )
        # Use configured workspace
        # If workspace is None, we use settings.workspace_dir dynamically via property
        self._custom_workspace = workspace
        if self._custom_workspace:
            self._custom_workspace.mkdir(parents=True, exist_ok=True)
        else:
            # Ensure default exists
            from app.config import settings
            settings.workspace_dir.mkdir(parents=True, exist_ok=True)

        # Context for audit logging
        self._agent_id: str | None = None
        self._session_id: str | None = None

    def set_context(self, agent_id: str | None = None, session_id: str | None = None) -> None:
        """Set context for audit logging."""
        self._agent_id = agent_id
        self._session_id = session_id

    def _get_allowed_dirs(self) -> list[Path]:
        """Get all directories where writes are allowed."""
        from app.config import get_allowed_write_dirs
        return get_allowed_write_dirs()

    def _get_validator(self) -> PathValidator:
        """Get a path validator instance."""
        return PathValidator(
            allowed_dirs=self._get_allowed_dirs(),
            workspace=self.workspace,
            follow_symlinks=True,
            max_symlink_depth=10,
        )

    def _is_write_allowed(self, path: Path) -> bool:
        """Check if path is within any allowed write directory."""
        try:
            resolved = path.resolve()
            for allowed_dir in self._get_allowed_dirs():
                allowed_resolved = allowed_dir.resolve()
                if str(resolved).startswith(str(allowed_resolved) + os.sep) or resolved == allowed_resolved:
                    return True
            return False
        except (OSError, ValueError):
            return False

    def _is_in_workspace(self, path: Path) -> bool:
        """Check if path is within the workspace directory (for display purposes)."""
        try:
            resolved = path.resolve()
            workspace_resolved = self.workspace.resolve()
            return str(resolved).startswith(str(workspace_resolved))
        except (OSError, ValueError):
            return False

    def _validate_path(
        self,
        path_str: str,
        operation: FileOperation,
        require_allowed: bool = False,
    ) -> tuple[Path | None, str | None]:
        """Validate and resolve a path with security checks.

        Returns (resolved_path, error_message)
        """
        return validate_and_audit(
            path_str=path_str,
            operation=operation,
            allowed_dirs=self._get_allowed_dirs(),
            workspace=self.workspace,
            require_allowed=require_allowed,
            agent_id=self._agent_id,
            session_id=self._session_id,
        )

    def _resolve_path(self, path: str, must_be_allowed: bool = False) -> tuple[Path, str | None]:
        """Resolve path, optionally checking write permission.

        Returns (resolved_path, error_message)

        NOTE: This is a legacy method - prefer _validate_path for new code.
        """
        # Determine operation type for validation
        operation = FileOperation.WRITE if must_be_allowed else FileOperation.READ

        resolved, error = self._validate_path(path, operation, must_be_allowed)

        if error:
            # Return a placeholder path with error for backwards compatibility
            p = Path(path).expanduser()
            if not p.is_absolute():
                p = self.workspace / p
            return p, error

        return resolved, None

    @property
    def workspace(self) -> Path:
        """Get current workspace path."""
        if self._custom_workspace:
            return self._custom_workspace
        from app.config import settings
        return settings.workspace_dir

    async def execute(self, **kwargs: Any) -> ToolResult:
        """Execute filesystem operation with security validation."""
        action = kwargs.get("action")
        path_str = kwargs.get("path", "")

        # Map action to FileOperation
        operation_map = {
            "read": FileOperation.READ,
            "list": FileOperation.LIST,
            "exists": FileOperation.EXISTS,
            "write": FileOperation.WRITE,
            "delete": FileOperation.DELETE,
            "copy": FileOperation.COPY,
        }
        operation = operation_map.get(action, FileOperation.READ)

        try:
            # === READ ACTIONS (allowed anywhere) ===
            if action == "read":
                path, error = self._validate_path(path_str, FileOperation.READ, require_allowed=False)
                if error:
                    return ToolResult(success=False, output="", error=error)

                if not path.exists():
                    security_audit.log_operation(
                        FileOperation.READ, path_str, str(path), success=False, allowed=True,
                        agent_id=self._agent_id, error="File not found"
                    )
                    return ToolResult(success=False, output="", error=f"File not found: {path}")
                if path.is_dir():
                    security_audit.log_operation(
                        FileOperation.READ, path_str, str(path), success=False, allowed=True,
                        agent_id=self._agent_id, error="Path is a directory"
                    )
                    return ToolResult(success=False, output="", error=f"Path is a directory: {path}")

                offset = int(kwargs.get("offset", 1)) - 1
                limit = int(kwargs.get("limit", 500))

                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()

                selected = lines[offset : offset + limit]
                content = "".join(selected)

                security_audit.log_operation(
                    FileOperation.READ, path_str, str(path), success=True, allowed=True,
                    agent_id=self._agent_id, details={"lines": len(selected), "bytes": len(content)}
                )

                return ToolResult(
                    success=True,
                    output=content,
                    data={
                        "path": str(path),
                        "total_lines": len(lines),
                        "returned_lines": len(selected),
                        "in_workspace": self._is_in_workspace(path),
                    },
                )

            elif action == "list":
                path, error = self._validate_path(path_str, FileOperation.LIST, require_allowed=False)
                if error:
                    return ToolResult(success=False, output="", error=error)

                if not path.exists():
                    security_audit.log_operation(
                        FileOperation.LIST, path_str, str(path), success=False, allowed=True,
                        agent_id=self._agent_id, error="Path not found"
                    )
                    return ToolResult(success=False, output="", error=f"Path not found: {path}")
                if path.is_file():
                    security_audit.log_operation(
                        FileOperation.LIST, path_str, str(path), success=True, allowed=True,
                        agent_id=self._agent_id
                    )
                    return ToolResult(success=True, output=str(path))

                items = []
                for item in sorted(path.iterdir()):
                    prefix = "📁 " if item.is_dir() else "📄 "
                    size = item.stat().st_size if item.is_file() else 0
                    items.append(f"{prefix}{item.name}" + (f" ({size} bytes)" if size else ""))

                security_audit.log_operation(
                    FileOperation.LIST, path_str, str(path), success=True, allowed=True,
                    agent_id=self._agent_id, details={"items": len(items)}
                )

                return ToolResult(
                    success=True,
                    output="\n".join(items) if items else "(empty directory)",
                    data={
                        "path": str(path),
                        "count": len(items),
                        "in_workspace": self._is_in_workspace(path),
                    },
                )

            elif action == "exists":
                path, error = self._validate_path(path_str, FileOperation.EXISTS, require_allowed=False)
                if error:
                    return ToolResult(success=False, output="", error=error)

                exists = path.exists()

                security_audit.log_operation(
                    FileOperation.EXISTS, path_str, str(path), success=True, allowed=True,
                    agent_id=self._agent_id, details={"exists": exists}
                )

                return ToolResult(
                    success=True,
                    output=f"{'Exists' if exists else 'Does not exist'}: {path}",
                    data={
                        "exists": exists,
                        "is_file": path.is_file() if exists else None,
                        "in_workspace": self._is_in_workspace(path),
                    },
                )

            # === WRITE ACTIONS (allowed directories only) ===
            elif action == "write":
                path, error = self._validate_path(path_str, FileOperation.WRITE, require_allowed=True)
                if error:
                    return ToolResult(success=False, output="", error=error)

                content = kwargs.get("content", "")

                # Additional security: verify parent dir is also in allowed path
                parent_path, parent_error = self._validate_path(
                    str(path.parent), FileOperation.CREATE_DIR, require_allowed=True
                )
                if parent_error:
                    return ToolResult(success=False, output="", error=f"Cannot create parent directory: {parent_error}")

                path.parent.mkdir(parents=True, exist_ok=True)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)

                security_audit.log_operation(
                    FileOperation.WRITE, path_str, str(path), success=True, allowed=True,
                    agent_id=self._agent_id, details={"bytes": len(content)}
                )

                return ToolResult(
                    success=True,
                    output=f"Written {len(content)} bytes to {path}",
                    data={"path": str(path), "bytes": len(content)},
                )

            elif action == "delete":
                path, error = self._validate_path(path_str, FileOperation.DELETE, require_allowed=True)
                if error:
                    return ToolResult(success=False, output="", error=error)

                if not path.exists():
                    security_audit.log_operation(
                        FileOperation.DELETE, path_str, str(path), success=False, allowed=True,
                        agent_id=self._agent_id, error="Path not found"
                    )
                    return ToolResult(success=False, output="", error=f"Path not found: {path}")

                # Additional security: don't delete allowed dir roots
                for allowed_dir in self._get_allowed_dirs():
                    if path.resolve() == allowed_dir.resolve():
                        security_audit.log_operation(
                            FileOperation.DELETE, path_str, str(path), success=False, allowed=False,
                            agent_id=self._agent_id, error="Cannot delete allowed directory root"
                        )
                        return ToolResult(success=False, output="", error="Cannot delete allowed directory root")

                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()

                security_audit.log_operation(
                    FileOperation.DELETE, path_str, str(path), success=True, allowed=True,
                    agent_id=self._agent_id
                )

                return ToolResult(success=True, output=f"Deleted {path}")

            elif action == "copy":
                # Validate source (read from anywhere)
                source, error = self._validate_path(path_str, FileOperation.READ, require_allowed=False)
                if error:
                    return ToolResult(success=False, output="", error=f"Source path error: {error}")

                dest_str = kwargs.get("dest")
                if not dest_str:
                    # Default: copy with same name into workspace root
                    dest_str = source.name

                # Validate destination (must be in allowed dirs)
                dest, error = self._validate_path(dest_str, FileOperation.WRITE, require_allowed=True)
                if error:
                    return ToolResult(success=False, output="", error=f"Destination error: {error}")

                if not source.exists():
                    security_audit.log_operation(
                        FileOperation.COPY, path_str, str(source), success=False, allowed=True,
                        agent_id=self._agent_id, error="Source not found"
                    )
                    return ToolResult(success=False, output="", error=f"Source not found: {source}")

                if source.is_dir():
                    if dest.exists():
                        shutil.rmtree(dest)
                    shutil.copytree(source, dest, symlinks=False)  # Don't copy symlinks
                    file_count = sum(1 for _ in dest.rglob("*") if _.is_file())

                    security_audit.log_operation(
                        FileOperation.COPY, path_str, str(dest), success=True, allowed=True,
                        agent_id=self._agent_id, details={"source": str(source), "files": file_count}
                    )

                    return ToolResult(
                        success=True,
                        output=f"Copied directory {source} → {dest} ({file_count} files)",
                        data={"source": str(source), "dest": str(dest), "files": file_count},
                    )
                else:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, dest)

                    security_audit.log_operation(
                        FileOperation.COPY, path_str, str(dest), success=True, allowed=True,
                        agent_id=self._agent_id, details={"source": str(source)}
                    )

                    return ToolResult(
                        success=True,
                        output=f"Copied {source} → {dest}",
                        data={"source": str(source), "dest": str(dest)},
                    )

            else:
                return ToolResult(success=False, output="", error=f"Unknown action: {action}")

        except PermissionError as e:
            security_audit.log_operation(
                operation, path_str, "N/A", success=False, allowed=False,
                agent_id=self._agent_id, error=f"Permission denied: {e}"
            )
            return ToolResult(success=False, output="", error=f"Permission denied: {e}")
        except Exception as e:
            security_audit.log_operation(
                operation, path_str, "N/A", success=False, allowed=True,
                agent_id=self._agent_id, error=str(e)
            )
            return ToolResult(success=False, output="", error=str(e))

    def get_workspace_info(self) -> dict[str, Any]:
        """Get workspace information."""
        return {
            "workspace": str(self.workspace),
            "exists": self.workspace.exists(),
            "allowed_dirs": [str(d) for d in self._get_allowed_dirs()],
        }

    def get_security_stats(self) -> dict[str, Any]:
        """Get security audit statistics."""
        return security_audit.get_stats()

    def get_recent_violations(self, limit: int = 20) -> list[dict[str, Any]]:
        """Get recent security violations."""
        return [v.to_dict() for v in security_audit.get_recent_violations(limit=limit)]

    def get_audit_log(self, limit: int = 50) -> list[dict[str, Any]]:
        """Get recent audit log entries."""
        return [e.to_dict() for e in security_audit.get_recent_entries(limit=limit)]


# Register the tool with default workspace
registry.register(FilesystemTool())
