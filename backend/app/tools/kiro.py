"""Kiro AI integration for MaratOS."""

import asyncio
import os
from typing import Any

from app.tools.base import Tool, ToolParameter, ToolResult, registry


class KiroTool(Tool):
    """Tool for delegating coding tasks to Kiro AI."""

    def __init__(self, timeout: int = 300) -> None:
        super().__init__(
            id="kiro",
            name="Kiro AI",
            description="Delegate coding tasks to Kiro AI - spec-driven development, code generation, and autonomous coding",
            parameters=[
                ToolParameter(
                    name="action",
                    type="string",
                    description="Action to perform",
                    enum=["prompt", "task", "status", "help"],
                ),
                ToolParameter(
                    name="message",
                    type="string",
                    description="Prompt or task description for Kiro",
                    required=False,
                ),
                ToolParameter(
                    name="workdir",
                    type="string",
                    description="Working directory for the task",
                    required=False,
                ),
                ToolParameter(
                    name="wait",
                    type="boolean",
                    description="Wait for task completion (for autonomous tasks)",
                    required=False,
                    default=True,
                ),
            ],
        )
        self.default_timeout = timeout

    async def execute(self, **kwargs: Any) -> ToolResult:
        """Execute Kiro command."""
        action = kwargs.get("action", "prompt")
        message = kwargs.get("message", "")
        workdir = kwargs.get("workdir")
        wait = kwargs.get("wait", True)

        # Check if Kiro CLI is installed
        check = await asyncio.create_subprocess_shell(
            "which kiro-cli || which kiro",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await check.communicate()
        
        if check.returncode != 0:
            return ToolResult(
                success=False,
                output="",
                error="Kiro CLI not installed. Install with: curl -fsSL https://cli.kiro.dev/install | bash",
            )

        try:
            # Detect the kiro command name
            kiro_cmd = stdout.decode().strip().split('\n')[0]
            
            if action == "help":
                # Get Kiro help
                process = await asyncio.create_subprocess_shell(
                    f"{kiro_cmd} --help",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await process.communicate()
                return ToolResult(
                    success=True,
                    output=stdout.decode("utf-8", errors="replace"),
                )

            elif action == "status":
                # Check Kiro status/auth
                process = await asyncio.create_subprocess_shell(
                    f"{kiro_cmd} auth status 2>&1 || {kiro_cmd} --version",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await process.communicate()
                output = stdout.decode("utf-8", errors="replace")
                if stderr:
                    output += "\n" + stderr.decode("utf-8", errors="replace")
                return ToolResult(
                    success=True,
                    output=output.strip(),
                )

            elif action == "prompt":
                # Interactive prompt to Kiro
                if not message:
                    return ToolResult(
                        success=False,
                        output="",
                        error="Message required for prompt action",
                    )

                # Use kiro with the prompt
                # Escape the message for shell
                escaped_message = message.replace("'", "'\\''")
                cmd = f"echo '{escaped_message}' | {kiro_cmd}"
                
                process = await asyncio.create_subprocess_shell(
                    cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=workdir,
                    env={**os.environ},
                )

                try:
                    stdout, stderr = await asyncio.wait_for(
                        process.communicate(), 
                        timeout=self.default_timeout
                    )
                except asyncio.TimeoutError:
                    process.kill()
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"Kiro timed out after {self.default_timeout}s",
                    )

                output = stdout.decode("utf-8", errors="replace")
                if stderr:
                    output += "\n[stderr]\n" + stderr.decode("utf-8", errors="replace")

                return ToolResult(
                    success=process.returncode == 0,
                    output=output.strip() or "(no output)",
                    error=None if process.returncode == 0 else f"Exit code: {process.returncode}",
                    data={"exit_code": process.returncode},
                )

            elif action == "task":
                # Start an autonomous task
                if not message:
                    return ToolResult(
                        success=False,
                        output="",
                        error="Message required for task action",
                    )

                escaped_message = message.replace("'", "'\\''")
                
                # Try to use kiro task command if available
                cmd = f"{kiro_cmd} task '{escaped_message}'"
                
                process = await asyncio.create_subprocess_shell(
                    cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=workdir,
                    env={**os.environ},
                )

                if wait:
                    try:
                        stdout, stderr = await asyncio.wait_for(
                            process.communicate(),
                            timeout=self.default_timeout
                        )
                    except asyncio.TimeoutError:
                        return ToolResult(
                            success=True,
                            output="Task started but timed out waiting. Check Kiro for status.",
                            data={"pid": process.pid, "status": "running"},
                        )
                else:
                    # Don't wait, return immediately
                    return ToolResult(
                        success=True,
                        output=f"Task started in background (pid: {process.pid})",
                        data={"pid": process.pid, "status": "started"},
                    )

                output = stdout.decode("utf-8", errors="replace")
                if stderr:
                    output += "\n[stderr]\n" + stderr.decode("utf-8", errors="replace")

                return ToolResult(
                    success=process.returncode == 0,
                    output=output.strip() or "(no output)",
                    error=None if process.returncode == 0 else f"Exit code: {process.returncode}",
                )

            else:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Unknown action: {action}. Use: prompt, task, status, help",
                )

        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))


# Register the tool
registry.register(KiroTool())
