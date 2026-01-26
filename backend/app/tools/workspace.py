"""Workspace management with cleanup and archival."""

import logging
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class WorkspaceStats:
    """Statistics about workspace usage."""
    total_size_bytes: int
    file_count: int
    dir_count: int
    oldest_file_age_days: float
    newest_file_age_days: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_size_mb": round(self.total_size_bytes / (1024 * 1024), 2),
            "total_size_bytes": self.total_size_bytes,
            "file_count": self.file_count,
            "dir_count": self.dir_count,
            "oldest_file_age_days": round(self.oldest_file_age_days, 1),
            "newest_file_age_days": round(self.newest_file_age_days, 1),
        }


@dataclass
class CleanupResult:
    """Result of a cleanup operation."""
    files_deleted: int
    bytes_freed: int
    errors: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "files_deleted": self.files_deleted,
            "mb_freed": round(self.bytes_freed / (1024 * 1024), 2),
            "bytes_freed": self.bytes_freed,
            "errors": self.errors,
        }


class WorkspaceManager:
    """Manages workspace cleanup and maintenance."""

    # Default patterns for temp files to clean
    TEMP_PATTERNS = [
        "*.tmp",
        "*.temp",
        "*.pyc",
        "__pycache__",
        ".pytest_cache",
        "*.log",
        ".DS_Store",
        "*.swp",
        "*.swo",
        "*~",
    ]

    # Patterns that should never be deleted automatically
    PROTECTED_PATTERNS = [
        ".git",
        ".gitignore",
        "README*",
        "LICENSE*",
        "requirements*.txt",
        "package*.json",
        "*.md",
    ]

    def __init__(self, workspace_dir: Path | None = None) -> None:
        self.workspace_dir = workspace_dir or settings.workspace_dir
        if isinstance(self.workspace_dir, str):
            self.workspace_dir = Path(self.workspace_dir).expanduser()

    def ensure_workspace_exists(self) -> Path:
        """Ensure workspace directory exists."""
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        return self.workspace_dir

    def get_stats(self) -> WorkspaceStats:
        """Get statistics about the workspace."""
        if not self.workspace_dir.exists():
            return WorkspaceStats(
                total_size_bytes=0,
                file_count=0,
                dir_count=0,
                oldest_file_age_days=0,
                newest_file_age_days=0,
            )

        total_size = 0
        file_count = 0
        dir_count = 0
        oldest_mtime = datetime.now()
        newest_mtime = datetime.now() - timedelta(days=365 * 10)  # Far in the past

        for root, dirs, files in os.walk(self.workspace_dir):
            dir_count += len(dirs)
            for filename in files:
                file_path = Path(root) / filename
                try:
                    stat = file_path.stat()
                    total_size += stat.st_size
                    file_count += 1

                    mtime = datetime.fromtimestamp(stat.st_mtime)
                    if mtime < oldest_mtime:
                        oldest_mtime = mtime
                    if mtime > newest_mtime:
                        newest_mtime = mtime
                except OSError:
                    pass

        now = datetime.now()
        return WorkspaceStats(
            total_size_bytes=total_size,
            file_count=file_count,
            dir_count=dir_count,
            oldest_file_age_days=(now - oldest_mtime).days if file_count > 0 else 0,
            newest_file_age_days=(now - newest_mtime).days if file_count > 0 else 0,
        )

    def cleanup_temp_files(self, patterns: list[str] | None = None) -> CleanupResult:
        """Delete temporary files matching patterns.

        Args:
            patterns: Glob patterns to match. Uses default TEMP_PATTERNS if None.

        Returns:
            CleanupResult with statistics.
        """
        patterns = patterns or self.TEMP_PATTERNS
        files_deleted = 0
        bytes_freed = 0
        errors = []

        if not self.workspace_dir.exists():
            return CleanupResult(0, 0, [])

        for pattern in patterns:
            for file_path in self.workspace_dir.rglob(pattern):
                # Skip protected patterns
                if any(file_path.match(p) for p in self.PROTECTED_PATTERNS):
                    continue

                try:
                    if file_path.is_file():
                        size = file_path.stat().st_size
                        file_path.unlink()
                        files_deleted += 1
                        bytes_freed += size
                        logger.debug(f"Deleted temp file: {file_path}")
                    elif file_path.is_dir():
                        size = sum(f.stat().st_size for f in file_path.rglob("*") if f.is_file())
                        shutil.rmtree(file_path)
                        files_deleted += 1
                        bytes_freed += size
                        logger.debug(f"Deleted temp dir: {file_path}")
                except OSError as e:
                    errors.append(f"Failed to delete {file_path}: {e}")

        logger.info(f"Temp cleanup: deleted {files_deleted} items, freed {bytes_freed} bytes")
        return CleanupResult(files_deleted, bytes_freed, errors)

    def cleanup_old_files(
        self,
        max_age_days: int = 30,
        min_size_bytes: int = 0,
    ) -> CleanupResult:
        """Delete files older than max_age_days.

        Args:
            max_age_days: Delete files older than this many days.
            min_size_bytes: Only delete files larger than this (0 = all).

        Returns:
            CleanupResult with statistics.
        """
        files_deleted = 0
        bytes_freed = 0
        errors = []
        cutoff = datetime.now() - timedelta(days=max_age_days)

        if not self.workspace_dir.exists():
            return CleanupResult(0, 0, [])

        for root, dirs, files in os.walk(self.workspace_dir):
            # Skip .git directories
            if ".git" in root:
                continue

            for filename in files:
                file_path = Path(root) / filename

                # Skip protected patterns
                if any(file_path.match(p) for p in self.PROTECTED_PATTERNS):
                    continue

                try:
                    stat = file_path.stat()
                    mtime = datetime.fromtimestamp(stat.st_mtime)

                    if mtime < cutoff and stat.st_size >= min_size_bytes:
                        file_path.unlink()
                        files_deleted += 1
                        bytes_freed += stat.st_size
                        logger.debug(f"Deleted old file: {file_path}")
                except OSError as e:
                    errors.append(f"Failed to delete {file_path}: {e}")

        logger.info(f"Old file cleanup: deleted {files_deleted} files, freed {bytes_freed} bytes")
        return CleanupResult(files_deleted, bytes_freed, errors)

    def cleanup_empty_dirs(self) -> CleanupResult:
        """Delete empty directories in workspace."""
        dirs_deleted = 0
        errors = []

        if not self.workspace_dir.exists():
            return CleanupResult(0, 0, [])

        # Walk bottom-up to delete empty directories
        for root, dirs, files in os.walk(self.workspace_dir, topdown=False):
            for dirname in dirs:
                dir_path = Path(root) / dirname

                # Skip protected directories
                if dirname in [".git", "__pycache__"]:
                    continue

                try:
                    if not any(dir_path.iterdir()):
                        dir_path.rmdir()
                        dirs_deleted += 1
                        logger.debug(f"Deleted empty dir: {dir_path}")
                except OSError as e:
                    errors.append(f"Failed to delete {dir_path}: {e}")

        logger.info(f"Empty dir cleanup: deleted {dirs_deleted} directories")
        return CleanupResult(dirs_deleted, 0, errors)

    def full_cleanup(
        self,
        max_age_days: int = 30,
        cleanup_temp: bool = True,
        cleanup_old: bool = True,
        cleanup_empty: bool = True,
    ) -> dict[str, Any]:
        """Perform full workspace cleanup.

        Returns:
            Dictionary with results from each cleanup step.
        """
        results = {}

        if cleanup_temp:
            results["temp_files"] = self.cleanup_temp_files().to_dict()

        if cleanup_old:
            results["old_files"] = self.cleanup_old_files(max_age_days).to_dict()

        if cleanup_empty:
            results["empty_dirs"] = self.cleanup_empty_dirs().to_dict()

        # Calculate totals
        total_deleted = sum(r.get("files_deleted", 0) for r in results.values())
        total_freed = sum(r.get("bytes_freed", 0) for r in results.values())
        total_errors = []
        for r in results.values():
            total_errors.extend(r.get("errors", []))

        results["summary"] = {
            "total_items_deleted": total_deleted,
            "total_mb_freed": round(total_freed / (1024 * 1024), 2),
            "total_errors": len(total_errors),
        }

        return results

    def get_large_files(self, min_size_mb: float = 10) -> list[dict[str, Any]]:
        """Find large files in workspace.

        Args:
            min_size_mb: Minimum size in MB to include.

        Returns:
            List of large files with their sizes.
        """
        min_size_bytes = int(min_size_mb * 1024 * 1024)
        large_files = []

        if not self.workspace_dir.exists():
            return []

        for file_path in self.workspace_dir.rglob("*"):
            if file_path.is_file():
                try:
                    size = file_path.stat().st_size
                    if size >= min_size_bytes:
                        large_files.append({
                            "path": str(file_path.relative_to(self.workspace_dir)),
                            "size_mb": round(size / (1024 * 1024), 2),
                            "size_bytes": size,
                        })
                except OSError:
                    pass

        # Sort by size descending
        large_files.sort(key=lambda x: x["size_bytes"], reverse=True)
        return large_files

    def archive_project(
        self,
        project_name: str,
        archive_dir: Path | None = None,
    ) -> Path | None:
        """Archive a project directory to a zip file.

        Args:
            project_name: Name of the project directory in workspace.
            archive_dir: Where to save archives. Defaults to workspace/.archives/

        Returns:
            Path to the archive file, or None if project not found.
        """
        project_path = self.workspace_dir / project_name
        if not project_path.exists():
            logger.warning(f"Project not found: {project_name}")
            return None

        archive_dir = archive_dir or (self.workspace_dir / ".archives")
        archive_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_name = f"{project_name}_{timestamp}"
        archive_path = archive_dir / archive_name

        try:
            shutil.make_archive(str(archive_path), "zip", project_path)
            logger.info(f"Archived project: {project_name} -> {archive_path}.zip")
            return Path(f"{archive_path}.zip")
        except Exception as e:
            logger.error(f"Failed to archive {project_name}: {e}")
            return None


# Global workspace manager
workspace_manager = WorkspaceManager()


def cleanup_kiro_temp_files() -> int:
    """Clean up Kiro CLI temporary files in /tmp."""
    files_deleted = 0

    # Clean up known Kiro temp files
    kiro_temp_patterns = [
        "/tmp/kiro_prompt*.txt",
        "/tmp/kiro_*.tmp",
    ]

    for pattern in kiro_temp_patterns:
        for file_path in Path("/tmp").glob(pattern.replace("/tmp/", "")):
            try:
                if file_path.is_file():
                    file_path.unlink()
                    files_deleted += 1
                    logger.debug(f"Deleted Kiro temp file: {file_path}")
            except OSError as e:
                logger.warning(f"Failed to delete {file_path}: {e}")

    if files_deleted > 0:
        logger.info(f"Cleaned up {files_deleted} Kiro temp files")

    return files_deleted
