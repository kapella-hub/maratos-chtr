"""Shell execution tool."""

import asyncio
import os
from typing import Any, AsyncIterator, Callable

from app.config import settings
from app.tools.base import Tool, ToolParameter, ToolResult, registry


# Type for activity callbacks
ActivityCallback = Callable[[str, dict[str, Any]], None]


class ShellTool(Tool):
    """Tool for executing shell commands."""

    def __init__(self, timeout: int | None = None) -> None:
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
                    default=settings.tool_timeout,
                ),
            ],
        )
        self.default_timeout = timeout or settings.tool_timeout

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

    async def execute_streaming(
        self,
        on_output: Callable[[str], None] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        """Execute shell command with streaming output.

        Args:
            on_output: Callback function called for each line of output
            **kwargs: Standard execute parameters (command, workdir, timeout)

        Returns:
            ToolResult with full output after command completes
        """
        command = kwargs.get("command", "")
        workdir = kwargs.get("workdir")
        timeout = int(kwargs.get("timeout", self.default_timeout))

        if not command:
            return ToolResult(success=False, output="", error="No command provided")

        try:
            # Create subprocess with pipes
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=workdir,
                env={**os.environ},
            )

            stdout_lines: list[str] = []
            stderr_lines: list[str] = []

            async def read_stream(stream: asyncio.StreamReader, lines: list[str], is_stderr: bool = False) -> None:
                """Read stream line by line and call callback."""
                while True:
                    try:
                        line = await asyncio.wait_for(stream.readline(), timeout=1.0)
                        if not line:
                            break
                        decoded = line.decode("utf-8", errors="replace").rstrip("\n\r")
                        lines.append(decoded)
                        if on_output and decoded.strip():
                            prefix = "[stderr] " if is_stderr else ""
                            on_output(f"{prefix}{decoded}")
                    except asyncio.TimeoutError:
                        # Check if process is still running
                        if process.returncode is not None:
                            break
                        continue

            # Read stdout and stderr concurrently with overall timeout
            try:
                await asyncio.wait_for(
                    asyncio.gather(
                        read_stream(process.stdout, stdout_lines, False),
                        read_stream(process.stderr, stderr_lines, True),
                    ),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                process.kill()
                return ToolResult(
                    success=False,
                    output="\n".join(stdout_lines),
                    error=f"Command timed out after {timeout}s",
                )

            # Wait for process to complete
            await process.wait()

            # Combine output
            output = "\n".join(stdout_lines)
            if stderr_lines:
                stderr_str = "\n".join(stderr_lines)
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

    async def stream_output(self, **kwargs: Any) -> AsyncIterator[str]:
        """Execute shell command and yield output lines as they arrive.

        This is an async generator that yields output line by line.

        Args:
            **kwargs: Standard execute parameters (command, workdir, timeout)

        Yields:
            Output lines as they are produced

        Returns:
            Final line contains result status as JSON
        """
        import json

        command = kwargs.get("command", "")
        workdir = kwargs.get("workdir")
        timeout = int(kwargs.get("timeout", self.default_timeout))

        if not command:
            yield json.dumps({"type": "error", "error": "No command provided"})
            return

        try:
            # Create subprocess
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=workdir,
                env={**os.environ},
            )

            start_time = asyncio.get_event_loop().time()
            stdout_lines: list[str] = []
            stderr_lines: list[str] = []

            async def read_and_yield(
                stream: asyncio.StreamReader,
                lines: list[str],
                stream_name: str,
            ) -> AsyncIterator[str]:
                """Read from stream and yield lines."""
                while True:
                    remaining = timeout - (asyncio.get_event_loop().time() - start_time)
                    if remaining <= 0:
                        break
                    try:
                        line = await asyncio.wait_for(stream.readline(), timeout=min(1.0, remaining))
                        if not line:
                            break
                        decoded = line.decode("utf-8", errors="replace").rstrip("\n\r")
                        lines.append(decoded)
                        yield json.dumps({"type": "output", "stream": stream_name, "line": decoded})
                    except asyncio.TimeoutError:
                        if process.returncode is not None:
                            break
                        continue

            # Interleave stdout and stderr
            async for line in read_and_yield(process.stdout, stdout_lines, "stdout"):
                yield line
            async for line in read_and_yield(process.stderr, stderr_lines, "stderr"):
                yield line

            await process.wait()

            # Final result
            output = "\n".join(stdout_lines)
            if stderr_lines:
                output += f"\n[stderr]\n" + "\n".join(stderr_lines)

            success = process.returncode == 0
            yield json.dumps({
                "type": "complete",
                "success": success,
                "exit_code": process.returncode,
                "output_lines": len(stdout_lines) + len(stderr_lines),
            })

        except asyncio.TimeoutError:
            process.kill()
            yield json.dumps({"type": "error", "error": f"Command timed out after {timeout}s"})
        except Exception as e:
            yield json.dumps({"type": "error", "error": str(e)})


# Register the tool
registry.register(ShellTool())
