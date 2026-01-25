"""Filesystem tools with sandboxed write access."""

import os
import shutil
from pathlib import Path
from typing import Any

from app.tools.base import Tool, ToolParameter, ToolResult, registry


class FilesystemTool(Tool):
    """Tool for filesystem operations with sandboxed writes.
    
    Security model:
    - READ: Allowed anywhere on the filesystem
    - WRITE: Only allowed in the workspace directory
    - When modifying external code, it must be copied to workspace first
    """

    def __init__(self, workspace: Path | None = None) -> None:
        super().__init__(
            id="filesystem",
            name="Filesystem",
            description="Read files anywhere, write only to workspace. Use 'copy' to bring external code into workspace for modification.",
            parameters=[
                ToolParameter(
                    name="action",
                    type="string",
                    description="Action: read (anywhere), list (anywhere), exists (anywhere), write/delete/copy (workspace only)",
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
                    description="Destination path in workspace (for copy action)",
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
        from app.config import settings
        self.workspace = workspace or settings.workspace_dir
        self.workspace.mkdir(parents=True, exist_ok=True)

    def _is_in_workspace(self, path: Path) -> bool:
        """Check if path is within the workspace directory."""
        try:
            resolved = path.resolve()
            workspace_resolved = self.workspace.resolve()
            return str(resolved).startswith(str(workspace_resolved))
        except (OSError, ValueError):
            return False

    def _resolve_path(self, path: str, must_be_workspace: bool = False) -> tuple[Path, str | None]:
        """Resolve path, optionally checking workspace restriction.
        
        Returns (resolved_path, error_message)
        """
        p = Path(path).expanduser()
        if not p.is_absolute():
            # Relative paths are relative to workspace
            p = self.workspace / p
        
        resolved = p.resolve()
        
        if must_be_workspace and not self._is_in_workspace(resolved):
            return resolved, f"Write operations only allowed in workspace ({self.workspace}). Use 'copy' action to bring files into workspace first."
        
        return resolved, None

    async def execute(self, **kwargs: Any) -> ToolResult:
        """Execute filesystem operation."""
        action = kwargs.get("action")
        path_str = kwargs.get("path", "")

        try:
            # === READ ACTIONS (allowed anywhere) ===
            if action == "read":
                path, _ = self._resolve_path(path_str, must_be_workspace=False)
                
                if not path.exists():
                    return ToolResult(success=False, output="", error=f"File not found: {path}")
                if path.is_dir():
                    return ToolResult(success=False, output="", error=f"Path is a directory: {path}")

                offset = int(kwargs.get("offset", 1)) - 1
                limit = int(kwargs.get("limit", 500))

                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()

                selected = lines[offset : offset + limit]
                content = "".join(selected)

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
                path, _ = self._resolve_path(path_str, must_be_workspace=False)
                
                if not path.exists():
                    return ToolResult(success=False, output="", error=f"Path not found: {path}")
                if path.is_file():
                    return ToolResult(success=True, output=str(path))

                items = []
                for item in sorted(path.iterdir()):
                    prefix = "📁 " if item.is_dir() else "📄 "
                    size = item.stat().st_size if item.is_file() else 0
                    items.append(f"{prefix}{item.name}" + (f" ({size} bytes)" if size else ""))

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
                path, _ = self._resolve_path(path_str, must_be_workspace=False)
                exists = path.exists()
                return ToolResult(
                    success=True,
                    output=f"{'Exists' if exists else 'Does not exist'}: {path}",
                    data={
                        "exists": exists, 
                        "is_file": path.is_file() if exists else None,
                        "in_workspace": self._is_in_workspace(path),
                    },
                )

            # === WRITE ACTIONS (workspace only) ===
            elif action == "write":
                path, error = self._resolve_path(path_str, must_be_workspace=True)
                if error:
                    return ToolResult(success=False, output="", error=error)

                content = kwargs.get("content", "")
                path.parent.mkdir(parents=True, exist_ok=True)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
                return ToolResult(
                    success=True,
                    output=f"Written {len(content)} bytes to {path}",
                    data={"path": str(path), "bytes": len(content)},
                )

            elif action == "delete":
                path, error = self._resolve_path(path_str, must_be_workspace=True)
                if error:
                    return ToolResult(success=False, output="", error=error)

                if not path.exists():
                    return ToolResult(success=False, output="", error=f"Path not found: {path}")
                
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()
                return ToolResult(success=True, output=f"Deleted {path}")

            elif action == "copy":
                # Copy from anywhere INTO workspace
                source, _ = self._resolve_path(path_str, must_be_workspace=False)
                
                dest_str = kwargs.get("dest")
                if not dest_str:
                    # Default: copy with same name into workspace root
                    dest_str = source.name
                
                dest, error = self._resolve_path(dest_str, must_be_workspace=True)
                if error:
                    return ToolResult(success=False, output="", error=error)

                if not source.exists():
                    return ToolResult(success=False, output="", error=f"Source not found: {source}")

                if source.is_dir():
                    if dest.exists():
                        shutil.rmtree(dest)
                    shutil.copytree(source, dest)
                    file_count = sum(1 for _ in dest.rglob("*") if _.is_file())
                    return ToolResult(
                        success=True,
                        output=f"Copied directory {source} → {dest} ({file_count} files)",
                        data={"source": str(source), "dest": str(dest), "files": file_count},
                    )
                else:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, dest)
                    return ToolResult(
                        success=True,
                        output=f"Copied {source} → {dest}",
                        data={"source": str(source), "dest": str(dest)},
                    )

            else:
                return ToolResult(success=False, output="", error=f"Unknown action: {action}")

        except PermissionError as e:
            return ToolResult(success=False, output="", error=f"Permission denied: {e}")
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    def get_workspace_info(self) -> dict[str, Any]:
        """Get workspace information."""
        return {
            "workspace": str(self.workspace),
            "exists": self.workspace.exists(),
        }


# Register the tool with default workspace
registry.register(FilesystemTool())
