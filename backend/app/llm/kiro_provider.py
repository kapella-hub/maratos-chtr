"""Kiro CLI provider for LLM access.

Routes all LLM calls through kiro-cli, providing streaming support
and compatibility with the existing agent architecture.
"""

import asyncio
import logging
import os
import re
from dataclasses import dataclass
from typing import Any, AsyncIterator

logger = logging.getLogger(__name__)


@dataclass
class KiroConfig:
    """Configuration for Kiro CLI provider."""

    model: str = "Auto"  # kiro-cli model name
    trust_tools: bool = True  # --trust-all-tools flag
    interactive: bool = False  # --no-interactive if False
    timeout: int = 300  # Timeout in seconds (5 min default)
    workdir: str | None = None  # Working directory for kiro


class KiroProvider:
    """LLM provider that routes all calls through kiro-cli.

    This replaces direct LiteLLM/Anthropic API calls with kiro-cli subprocess
    execution, enabling use in environments where kiro-cli is the only
    approved AI access method.
    """

    def __init__(self) -> None:
        self._kiro_cmd: str | None = None
        self._available: bool | None = None

    async def _get_kiro_cmd(self) -> str | None:
        """Find the kiro-cli command in PATH."""
        if self._kiro_cmd:
            return self._kiro_cmd

        for cmd in ["kiro-cli", "kiro"]:
            try:
                check = await asyncio.create_subprocess_shell(
                    f"which {cmd}",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await check.communicate()
                if check.returncode == 0:
                    self._kiro_cmd = stdout.decode().strip()
                    logger.info(f"Found kiro-cli at: {self._kiro_cmd}")
                    return self._kiro_cmd
            except Exception as e:
                logger.debug(f"Error checking for {cmd}: {e}")

        logger.error("kiro-cli not found in PATH")
        return None

    async def is_available(self) -> bool:
        """Check if kiro-cli is available."""
        if self._available is not None:
            return self._available

        cmd = await self._get_kiro_cmd()
        self._available = cmd is not None
        return self._available

    async def get_version(self) -> str | None:
        """Get kiro-cli version."""
        cmd = await self._get_kiro_cmd()
        if not cmd:
            return None

        try:
            process = await asyncio.create_subprocess_shell(
                f"{cmd} --version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await process.communicate()
            return stdout.decode().strip()
        except Exception as e:
            logger.error(f"Error getting kiro version: {e}")
            return None

    def _strip_ansi(self, text: str) -> str:
        """Remove ANSI escape codes from text."""
        ansi_pattern = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]|\x1b\][^\x07]*\x07|\[\?25[hl]')
        return ansi_pattern.sub('', text)

    def _clean_output(self, text: str) -> str:
        """Remove kiro-cli ASCII art, ANSI codes, and formatting artifacts."""
        if not text:
            return text

        # First strip ANSI codes
        text = self._strip_ansi(text)

        lines = text.split('\n')
        cleaned = []
        skip_banner = False
        in_response = False

        for line in lines:
            # Skip ASCII art banner (Unicode box/block characters)
            special_chars = '⠀▀▄█░▒▓│╭╮╯╰─┌┐└┘├┤┬┴┼⣴⣶⣦⣿⢰⢸⠈⠙⠁'
            special_count = sum(1 for c in line if c in special_chars)
            if special_count > len(line) * 0.3 and len(line) > 10:
                continue

            # Skip "Did you know?" tips and similar banners
            if 'Did you know?' in line or '─────' in line or '╭──' in line or '╰──' in line:
                skip_banner = True
                continue
            if skip_banner:
                if not line.strip() or '╰──' in line:
                    skip_banner = False
                continue

            # Skip model selection line
            if 'Model:' in line and ('Auto' in line or 'claude' in line):
                continue

            # Skip tool approval messages
            if 'tools are now trusted' in line or 'trust-all' in line:
                continue
            if 'Agents can sometimes' in line or 'Learn more at' in line:
                continue
            if 'kiro.dev/docs' in line:
                continue

            # Skip timing info at the end
            if line.strip().startswith('▸ Time:') or line.strip().startswith('Time:'):
                continue

            # Detect response start (often prefixed with "> ")
            if line.startswith('> '):
                in_response = True
                cleaned.append(line[2:])  # Remove "> " prefix
                continue

            # Skip lines before response starts (usually empty or control chars)
            if not in_response and not line.strip():
                continue

            # Once we're in response, include content
            if in_response or line.strip():
                cleaned.append(line)

        # Remove excessive empty lines
        result = '\n'.join(cleaned)
        result = re.sub(r'\n{3,}', '\n\n', result)
        return result.strip()

    def _format_messages_as_prompt(
        self,
        messages: list[dict[str, Any]],
        include_system: bool = True,
    ) -> str:
        """Convert message list to a single prompt string for kiro-cli.

        Args:
            messages: List of message dicts with 'role' and 'content'
            include_system: Whether to include system messages

        Returns:
            Formatted prompt string
        """
        parts = []

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if not content:
                continue

            if role == "system":
                if include_system:
                    # Include system prompt as context
                    parts.append(f"<system_context>\n{content}\n</system_context>\n")
            elif role == "user":
                parts.append(f"User: {content}\n")
            elif role == "assistant":
                parts.append(f"Assistant: {content}\n")
            elif role == "tool":
                # Tool results from previous calls
                parts.append(f"Tool Result: {content}\n")

        # Add final instruction for the assistant to respond
        if parts and not parts[-1].startswith("User:"):
            parts.append("\nPlease respond to the above conversation.")

        return "\n".join(parts)

    async def chat_completion(
        self,
        messages: list[dict[str, Any]],
        config: KiroConfig | None = None,
    ) -> str:
        """Non-streaming chat completion.

        Args:
            messages: List of message dicts
            config: Optional Kiro configuration

        Returns:
            Complete response text
        """
        config = config or KiroConfig()
        response_parts = []

        async for chunk in self.chat_completion_stream(messages, config):
            response_parts.append(chunk)

        return "".join(response_parts)

    async def chat_completion_stream(
        self,
        messages: list[dict[str, Any]],
        config: KiroConfig | None = None,
    ) -> AsyncIterator[str]:
        """Streaming chat completion via kiro-cli.

        Note: kiro-cli doesn't truly stream - it outputs all at once.
        We collect the output and yield cleaned content.

        Args:
            messages: List of message dicts with 'role' and 'content'
            config: Optional Kiro configuration

        Yields:
            Response text chunks
        """
        config = config or KiroConfig()
        kiro_cmd = await self._get_kiro_cmd()

        if not kiro_cmd:
            yield "Error: kiro-cli not found. Please install: curl -fsSL https://cli.kiro.dev/install | bash"
            return

        # Build command
        cmd = [kiro_cmd, "chat"]

        # Add model flag if not Auto
        if config.model and config.model != "Auto":
            cmd.extend(["--model", config.model])

        # Add trust and interactive flags
        if config.trust_tools:
            cmd.append("--trust-all-tools")
        if not config.interactive:
            cmd.append("--no-interactive")

        # Format messages as prompt
        prompt = self._format_messages_as_prompt(messages)

        logger.info(f"Kiro command: {' '.join(cmd)}")
        logger.debug(f"Prompt length: {len(prompt)} chars")

        try:
            # Create subprocess with pipes
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=config.workdir,
                env={**os.environ},
            )

            # Send prompt to stdin and close
            process.stdin.write(prompt.encode("utf-8"))
            await process.stdin.drain()
            process.stdin.close()

            # Collect all output (kiro-cli doesn't truly stream)
            try:
                async with asyncio.timeout(config.timeout):
                    stdout, stderr = await process.communicate()
            except asyncio.TimeoutError:
                logger.error(f"Kiro CLI timed out after {config.timeout}s")
                process.kill()
                yield f"Error: Request timed out after {config.timeout} seconds"
                return

            # Decode output
            raw_output = stdout.decode("utf-8", errors="replace")
            stderr_text = stderr.decode("utf-8", errors="replace")

            # Log stderr (usually contains the banner)
            if stderr_text and 'warning' not in stderr_text.lower():
                logger.debug(f"Kiro stderr length: {len(stderr_text)}")

            # Clean the output
            cleaned = self._clean_output(raw_output)

            if cleaned:
                # Yield the cleaned content in chunks for streaming feel
                chunk_size = 50
                for i in range(0, len(cleaned), chunk_size):
                    yield cleaned[i:i + chunk_size]
                    await asyncio.sleep(0.01)  # Small delay for streaming effect
            else:
                logger.warning(f"No content extracted from kiro output (raw length: {len(raw_output)})")
                # Try to extract anything useful
                stripped = self._strip_ansi(raw_output)
                if '> ' in stripped:
                    # Extract content after "> " marker
                    parts = stripped.split('> ', 1)
                    if len(parts) > 1:
                        content = parts[1].split('\n')[0].strip()
                        if content:
                            yield content

            if process.returncode != 0:
                logger.error(f"Kiro exited with code {process.returncode}")

        except FileNotFoundError:
            logger.error("kiro-cli executable not found")
            yield "Error: kiro-cli not found in PATH"
        except Exception as e:
            logger.error(f"Kiro chat error: {e}", exc_info=True)
            yield f"Error: {str(e)}"

    async def generate_short_response(
        self,
        prompt: str,
        max_length: int = 100,
        config: KiroConfig | None = None,
    ) -> str:
        """Generate a short response (e.g., for titles).

        Args:
            prompt: The prompt to send
            max_length: Maximum response length
            config: Optional Kiro configuration

        Returns:
            Short response text
        """
        config = config or KiroConfig()

        # Use a simpler prompt format for short responses
        full_prompt = f"""Generate a brief response (max {max_length} characters).
Return ONLY the response, no explanation or quotes.

{prompt}"""

        messages = [{"role": "user", "content": full_prompt}]

        response = await self.chat_completion(messages, config)

        # Clean and truncate
        response = self._clean_output(response)
        response = response.strip().strip('"\'')

        if len(response) > max_length:
            response = response[:max_length-3] + "..."

        return response


# Global singleton instance
kiro_provider = KiroProvider()
