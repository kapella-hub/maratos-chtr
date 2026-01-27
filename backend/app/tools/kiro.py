"""Kiro AI integration - tuned for quality over speed."""

import asyncio
import os
from typing import Any

from app.tools.base import Tool, ToolParameter, ToolResult, registry


# Quality-focused prompt templates for Kiro
ARCHITECTURE_PROMPT = """You are working on a critical task that requires careful architecture and design.

BEFORE implementing, you MUST:
1. Analyze the existing codebase structure
2. Identify all dependencies and constraints  
3. Consider at least 2 alternative approaches
4. Document trade-offs for each approach
5. Choose the best approach and explain why

DURING implementation:
- Write clean, well-documented code
- Follow existing code conventions
- Handle all error cases
- Consider edge cases
- Add appropriate logging

AFTER implementing:
- Review your own code for issues
- Verify error handling is complete
- Ensure the solution is testable
- Document any non-obvious decisions

Task: {task}

Working directory: {workdir}
"""

VALIDATION_PROMPT = """Review and validate the following code changes for:

1. CORRECTNESS
   - Does it do what it's supposed to?
   - Are there logic errors?
   - Edge cases handled?

2. SECURITY
   - Input validation?
   - No injection vulnerabilities?
   - Sensitive data protected?

3. PERFORMANCE
   - Obvious inefficiencies?
   - Appropriate algorithms?
   - No unnecessary operations?

4. MAINTAINABILITY  
   - Code is readable?
   - Follows conventions?
   - Adequate documentation?

5. TESTING
   - What tests are needed?
   - What edge cases to test?

Provide specific findings with line numbers and suggested fixes.

Files to review: {files}
Working directory: {workdir}
"""

TESTING_PROMPT = """Generate comprehensive tests for the following code.

Requirements:
1. Unit tests for all public functions/methods
2. Edge case coverage (null, empty, boundary values)
3. Error case coverage (invalid inputs, failures)
4. Integration tests if applicable
5. Use the project's existing test framework

For each test:
- Clear test name describing what's tested
- Arrange-Act-Assert structure
- Meaningful assertions
- Comments for complex test logic

Code to test: {files}
Working directory: {workdir}
"""


class KiroTool(Tool):
    """Kiro AI integration - ANALYSIS ONLY, no file writing."""

    def __init__(self, timeout: int | None = None) -> None:  # No timeout - work until done
        super().__init__(
            id="kiro",
            name="Kiro AI",
            description="AI code analysis - validate (review), test (generate tests), prompt (questions). Does NOT write files.",
            parameters=[
                ToolParameter(
                    name="action",
                    type="string",
                    description="Action: validate (review code), test (generate test suggestions), prompt (analysis/questions), status",
                    enum=["validate", "test", "prompt", "status"],
                ),
                ToolParameter(
                    name="task",
                    type="string",
                    description="Task description or prompt for Kiro",
                    required=False,
                ),
                ToolParameter(
                    name="files",
                    type="string",
                    description="Files to review/test (comma-separated paths)",
                    required=False,
                ),
                ToolParameter(
                    name="workdir",
                    type="string",
                    description="Working directory for the task",
                    required=False,
                ),
                ToolParameter(
                    name="spec",
                    type="string",
                    description="Additional specifications or constraints",
                    required=False,
                ),
            ],
        )
        self._kiro_cmd: str | None = None

    async def _get_kiro_cmd(self) -> str | None:
        """Find the Kiro CLI command."""
        if self._kiro_cmd:
            return self._kiro_cmd
            
        for cmd in ["kiro-cli", "kiro"]:
            check = await asyncio.create_subprocess_shell(
                f"which {cmd}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await check.communicate()
            if check.returncode == 0:
                self._kiro_cmd = stdout.decode().strip()
                return self._kiro_cmd
        
        return None

    def _clean_kiro_output(self, output: str) -> str:
        """Remove Kiro ASCII art banner and spinner artifacts from output."""
        lines = output.split('\n')
        cleaned_lines = []
        in_banner = False

        for line in lines:
            # Skip ASCII art banner (contains special Unicode box drawing chars)
            if '╭─' in line or '╰─' in line or '│' in line:
                continue
            # Skip lines that are mostly Unicode art characters
            if line.count('⠀') > 5 or line.count('█') > 3 or line.count('▀') > 3 or line.count('▄') > 3:
                continue
            # Skip model selection line
            if line.strip().startswith('Model:'):
                continue
            # Skip "Did you know" tips
            if 'Did you know?' in line or '/changelog' in line:
                in_banner = True
                continue
            if in_banner and line.strip() == '':
                in_banner = False
                continue
            if in_banner:
                continue
            # Skip empty lines at start
            if not cleaned_lines and not line.strip():
                continue
            cleaned_lines.append(line)

        # Remove trailing empty lines
        while cleaned_lines and not cleaned_lines[-1].strip():
            cleaned_lines.pop()

        return '\n'.join(cleaned_lines)

    async def _run_kiro(self, prompt: str, workdir: str | None = None) -> ToolResult:
        """Run Kiro with a prompt."""
        kiro_cmd = await self._get_kiro_cmd()
        if not kiro_cmd:
            return ToolResult(
                success=False,
                output="",
                error="Kiro CLI not found. Install: curl -fsSL https://cli.kiro.dev/install | bash",
            )

        # Kiro CLI chat subcommand with trust flags
        # --trust-all-tools: Auto-approve all tool usage
        # --no-interactive: Don't prompt for input
        # Use subprocess with stdin pipe to pass the prompt
        cmd = [kiro_cmd, "chat", "--trust-all-tools", "--no-interactive"]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=workdir,
            env={**os.environ},
        )

        # Send prompt via stdin and wait for completion
        stdout, stderr = await process.communicate(input=prompt.encode("utf-8"))

        output = stdout.decode("utf-8", errors="replace")
        stderr_text = stderr.decode("utf-8", errors="replace")

        # Check for permission errors
        if "Tool approval" in output or "permission" in stderr_text.lower():
            return ToolResult(
                success=False,
                output="",
                error=f"Kiro CLI permission error. {stderr_text or output}",
            )

        # Clean the output to remove ASCII art and banners
        output = self._clean_kiro_output(output)

        if stderr_text.strip() and 'warning' not in stderr_text.lower():
            output += f"\n[stderr]\n{self._clean_kiro_output(stderr_text)}"

        return ToolResult(
            success=process.returncode == 0,
            output=output.strip() or "(no output)",
            error=None if process.returncode == 0 else f"Exit code: {process.returncode}",
            data={"exit_code": process.returncode},
        )

    async def execute(self, **kwargs: Any) -> ToolResult:
        """Execute Kiro action."""
        action = kwargs.get("action", "prompt")
        task = kwargs.get("task", "")
        files = kwargs.get("files", "")
        workdir = kwargs.get("workdir", os.getcwd())
        spec = kwargs.get("spec", "")

        if action == "status":
            kiro_cmd = await self._get_kiro_cmd()
            if not kiro_cmd:
                return ToolResult(
                    success=False,
                    output="Kiro CLI not installed",
                    error="Install: curl -fsSL https://cli.kiro.dev/install | bash",
                )
            
            process = await asyncio.create_subprocess_shell(
                f"{kiro_cmd} --version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await process.communicate()
            return ToolResult(
                success=True,
                output=f"Kiro CLI: {stdout.decode().strip()}\nPath: {kiro_cmd}",
            )

        elif action == "validate":
            if not files:
                return ToolResult(success=False, output="", error="Files required for validate action")
            
            prompt = VALIDATION_PROMPT.format(files=files, workdir=workdir)
            if spec:
                prompt += f"\n\nFocus areas:\n{spec}"
            
            return await self._run_kiro(prompt, workdir)

        elif action == "test":
            if not files:
                return ToolResult(success=False, output="", error="Files required for test action")
            
            prompt = TESTING_PROMPT.format(files=files, workdir=workdir)
            if spec:
                prompt += f"\n\nTest requirements:\n{spec}"
            
            return await self._run_kiro(prompt, workdir)

        elif action == "prompt":
            if not task:
                return ToolResult(success=False, output="", error="Task/prompt required")

            # Add quality guidelines - ANALYSIS ONLY, no file writing
            quality_prefix = """IMPORTANT: You are in ANALYSIS mode only.
- DO NOT write or modify any files
- Analyze and explain code
- Suggest improvements
- Answer questions
- If asked to implement something, provide the code as text output only

"""
            prompt = quality_prefix + task
            if spec:
                prompt += f"\n\nConstraints:\n{spec}"

            return await self._run_kiro(prompt, workdir)

        else:
            return ToolResult(
                success=False,
                output="",
                error=f"Unknown action: {action}. Use: validate, test, prompt, status",
            )


# Register the tool
registry.register(KiroTool())
