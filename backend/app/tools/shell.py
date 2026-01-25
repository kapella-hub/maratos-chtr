"""Shell execution tool."""

import asyncio
import os
from typing import Any

from app.tools.base import Tool, ToolParameter, ToolResult, registry


class ShellTool(Tool):
    """Tool for executing shell commands."""

    def __init__(self, timeout: int = 60) -> None:
        super().__init__(
            id="shell",
            name="Shell",
            description="Execute shell commands",
            parameters=[
                ToolParameter(
                    name="command",
                    type="string",
                    description="Shell command to execute",
                ),
                ToolParameter(
                    name="workdir",
                    type="string",
                    description="Working directory for the command",
                    required=False,
                ),
                ToolParameter(
                    name="timeout",
                    type="number",
                    description="Timeout in seconds",
                    required=False,
                    default=60,
                ),
            ],
        )
        self.default_timeout = timeout

    async def execute(self, **kwargs: Any) -> ToolResult:
        """Execute shell command."""
        command = kwargs.get("command", "")
        workdir = kwargs.get("workdir")
        timeout = int(kwargs.get("timeout", self.default_timeout))

        if not command:
            return ToolResult(success=False, output="", error="No command provided")

        try:
            # Create subprocess
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=workdir,
                env={**os.environ},
            )

            # Wait with timeout
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Command timed out after {timeout}s",
                )

            stdout_str = stdout.decode("utf-8", errors="replace")
            stderr_str = stderr.decode("utf-8", errors="replace")

            # Combine output
            output = stdout_str
            if stderr_str:
                output += f"\n[stderr]\n{stderr_str}" if output else stderr_str

            success = process.returncode == 0

            return ToolResult(
                success=success,
                output=output.strip() or "(no output)",
                error=None if success else f"Exit code: {process.returncode}",
                data={"exit_code": process.returncode},
            )

        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))


# Register the tool
registry.register(ShellTool())
