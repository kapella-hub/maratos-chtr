"""Git operations for autonomous projects."""

import asyncio
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class GitResult:
    """Result of a git operation."""
    success: bool
    output: str
    error: str | None = None


class GitOperations:
    """Git operations for autonomous projects."""

    def __init__(self, workdir: str | Path) -> None:
        self.workdir = Path(workdir)

    async def _run_command(self, *args: str) -> GitResult:
        """Run a git command."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "git",
                *args,
                cwd=self.workdir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode == 0:
                return GitResult(
                    success=True,
                    output=stdout.decode().strip(),
                )
            else:
                return GitResult(
                    success=False,
                    output=stdout.decode().strip(),
                    error=stderr.decode().strip(),
                )
        except Exception as e:
            logger.error(f"Git command failed: {e}")
            return GitResult(success=False, output="", error=str(e))

    async def is_git_repo(self) -> bool:
        """Check if the workdir is a git repository."""
        result = await self._run_command("rev-parse", "--git-dir")
        return result.success

    async def init(self) -> GitResult:
        """Initialize a git repository."""
        return await self._run_command("init")

    async def get_current_branch(self) -> str | None:
        """Get the current branch name."""
        result = await self._run_command("branch", "--show-current")
        return result.output if result.success else None

    async def create_branch(self, branch_name: str) -> GitResult:
        """Create and checkout a new branch."""
        result = await self._run_command("checkout", "-b", branch_name)
        if not result.success:
            # Branch might exist, try to checkout
            result = await self._run_command("checkout", branch_name)
        return result

    async def checkout(self, branch_name: str) -> GitResult:
        """Checkout a branch."""
        return await self._run_command("checkout", branch_name)

    async def status(self) -> dict[str, Any]:
        """Get git status."""
        result = await self._run_command("status", "--porcelain")
        if not result.success:
            return {"error": result.error}

        modified = []
        added = []
        deleted = []
        untracked = []

        for line in result.output.split("\n"):
            if not line:
                continue
            status_code = line[:2]
            filepath = line[3:]

            if status_code[0] == "?" or status_code[1] == "?":
                untracked.append(filepath)
            elif status_code[0] == "M" or status_code[1] == "M":
                modified.append(filepath)
            elif status_code[0] == "A" or status_code[1] == "A":
                added.append(filepath)
            elif status_code[0] == "D" or status_code[1] == "D":
                deleted.append(filepath)

        return {
            "modified": modified,
            "added": added,
            "deleted": deleted,
            "untracked": untracked,
            "has_changes": bool(modified or added or deleted or untracked),
        }

    async def add(self, *files: str) -> GitResult:
        """Stage files for commit."""
        if not files:
            return await self._run_command("add", "-A")
        return await self._run_command("add", *files)

    async def commit(self, message: str, allow_empty: bool = False) -> GitResult:
        """Create a commit."""
        args = ["commit", "-m", message]
        if allow_empty:
            args.append("--allow-empty")
        return await self._run_command(*args)

    async def get_last_commit_sha(self) -> str | None:
        """Get the SHA of the last commit."""
        result = await self._run_command("rev-parse", "HEAD")
        return result.output[:8] if result.success else None

    async def get_changed_files(self, since_commit: str | None = None) -> list[str]:
        """Get list of files changed since a commit."""
        if since_commit:
            result = await self._run_command("diff", "--name-only", since_commit, "HEAD")
        else:
            result = await self._run_command("diff", "--name-only", "HEAD~1", "HEAD")

        if result.success:
            return [f for f in result.output.split("\n") if f]
        return []

    async def push(self, remote: str = "origin", branch: str | None = None, set_upstream: bool = True) -> GitResult:
        """Push to remote."""
        args = ["push"]
        if set_upstream:
            args.extend(["-u", remote])
            if branch:
                args.append(branch)
        else:
            args.append(remote)
            if branch:
                args.append(branch)
        return await self._run_command(*args)

    async def has_remote(self, remote: str = "origin") -> bool:
        """Check if remote exists."""
        result = await self._run_command("remote", "get-url", remote)
        return result.success

    async def get_remote_url(self, remote: str = "origin") -> str | None:
        """Get the URL of a remote."""
        result = await self._run_command("remote", "get-url", remote)
        return result.output if result.success else None

    async def create_pull_request(
        self,
        title: str,
        body: str,
        base: str = "main",
        head: str | None = None,
    ) -> dict[str, Any]:
        """Create a pull request using gh CLI."""
        if head is None:
            head = await self.get_current_branch()

        # Use gh CLI to create PR
        try:
            proc = await asyncio.create_subprocess_exec(
                "gh",
                "pr",
                "create",
                "--title",
                title,
                "--body",
                body,
                "--base",
                base,
                "--head",
                head or "",
                cwd=self.workdir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode == 0:
                pr_url = stdout.decode().strip()
                # Extract PR number from URL
                match = re.search(r"/pull/(\d+)", pr_url)
                pr_number = match.group(1) if match else None

                return {
                    "success": True,
                    "url": pr_url,
                    "number": pr_number,
                }
            else:
                return {
                    "success": False,
                    "error": stderr.decode().strip(),
                }
        except FileNotFoundError:
            return {
                "success": False,
                "error": "gh CLI not installed. Install from https://cli.github.com/",
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }

    async def stash(self) -> GitResult:
        """Stash current changes."""
        return await self._run_command("stash")

    async def stash_pop(self) -> GitResult:
        """Pop stashed changes."""
        return await self._run_command("stash", "pop")

    async def reset_hard(self, commit: str = "HEAD") -> GitResult:
        """Hard reset to a commit (use with caution!)."""
        return await self._run_command("reset", "--hard", commit)

    async def diff(self, file: str | None = None, staged: bool = False) -> str:
        """Get diff output."""
        args = ["diff"]
        if staged:
            args.append("--cached")
        if file:
            args.append(file)
        result = await self._run_command(*args)
        return result.output if result.success else ""

    async def log(self, count: int = 10, oneline: bool = True) -> list[dict[str, str]]:
        """Get commit log."""
        if oneline:
            result = await self._run_command("log", f"-{count}", "--oneline")
            if not result.success:
                return []
            commits = []
            for line in result.output.split("\n"):
                if line:
                    parts = line.split(" ", 1)
                    commits.append({
                        "sha": parts[0],
                        "message": parts[1] if len(parts) > 1 else "",
                    })
            return commits
        else:
            result = await self._run_command(
                "log",
                f"-{count}",
                "--format=%H|%s|%an|%ai",
            )
            if not result.success:
                return []
            commits = []
            for line in result.output.split("\n"):
                if line:
                    parts = line.split("|")
                    commits.append({
                        "sha": parts[0],
                        "message": parts[1] if len(parts) > 1 else "",
                        "author": parts[2] if len(parts) > 2 else "",
                        "date": parts[3] if len(parts) > 3 else "",
                    })
            return commits
