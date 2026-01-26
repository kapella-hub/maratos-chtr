"""Kiro CLI agent - uses kiro-cli for Claude models via AWS."""

import asyncio
import re
import shutil
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from app.agents.base import Agent, AgentConfig

# Regex to strip ANSI escape codes
ANSI_ESCAPE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

# Patterns for verbose tool logs to filter out (line-based)
TOOL_LOG_PATTERNS = [
    r'^Reading (?:directory|file):.*',
    r'^Batch \w+ operation.*',
    r'^↱ Operation \d+:.*',
    r'^[✓✔☑✗✘❌]\s*(?:Successfully|Failed).*',  # Various checkmark/x characters
    r'^(?:Successfully|Failed)\s+(?:read|wrote|deleted|copied).*',  # Without checkmark
    r'^⋮\s*$',  # Just the ellipsis character alone
    r'^⋮.*',  # Ellipsis with anything after
    r'^\s*Summary:.*',
    r'^•?\s*Completed in.*',  # With or without bullet
    r'.*\(using tool:.*\).*',
    r'^\d+;\d+m.*entries.*',
    r'^\s*\[\d+ more items found\].*',
    r'^\[Overview\].*bytes.*tokens.*',
    r'^\d+ \w+ at /.*:\d+:\d+$',  # "1 Class RequestData at /path:30:1"
    r'^\(\d+ more items found\)$',
    r'^Searching.*\.\.\..*',  # "Searching in /path..."
    r'^Found \d+ (?:files?|matches?).*',  # "Found 5 files..."
    r'^Purpose:.*',  # "Purpose: ..."
    r'^Updating:.*',  # "Updating: path"
    r'^Creating:.*',  # "Creating: path"
    r'^Deleting:.*',  # "Deleting: path"
    r'^\d+ operations? processed.*',  # "2 operations processed, 2 successful"
    # Kiro CLI startup noise
    r'^Model:.*$',  # "Model: claude-sonnet-4 (/model to change)"
    r'^Did you know\?.*$',
    r'^You can use.*$',
    r'^\s*experience\s*$',
    r'^Time:.*$',
    r'^\s*▸\s*Time:.*$',  # " ▸ Time: 2s"
    r'^[•\-\s]*Completed in \d+\.?\d*s?.*$',  # " - Completed in 0.0s"
    r'^Now let me analyze.*$',
    r'^Let me start by reading.*$',
    r'^I\'ll (?:start|begin|conduct|analyze|review).*$',  # Transitional phrases
]

# Pattern for kiro banner (ASCII art and boxes)
KIRO_BANNER_PATTERNS = [
    r'^[╭╮╰╯│─]+',  # Box drawing characters
    r'^\s*[⢀⣴⣶⣦⡀⠀⣾⣿⠋⠁⠈⠙⡆⢀⢻⡆⢰⣇⡿⠀⣼⠇⢸⣤⣄⠉⡇⠹⣷⣆⣸⣠⣿⠃⢿⢹⣧⠻⣦⢴⠟⣤⣼⢀⣠⣴⣤⣄⡀⠈⠙⣷⡀⣶⡄⢸⠹⠁]+',  # Kiro banner characters
    r'^\s*$',  # Empty lines in the banner area
]

def is_tool_log_line(line: str) -> bool:
    """Check if a line is a tool execution log."""
    # Check tool log patterns
    for pattern in TOOL_LOG_PATTERNS:
        if re.match(pattern, line):
            return True
    # Check banner patterns
    for pattern in KIRO_BANNER_PATTERNS:
        if re.match(pattern, line):
            return True
    return False

def is_kiro_banner_line(line: str) -> bool:
    """Check if line is part of the Kiro ASCII banner."""
    # Banner contains these specific Unicode characters
    banner_chars = set('⢀⣴⣶⣦⡀⠀⣾⣿⠋⠁⠈⠙⡆⢻⢰⣇⡿⣼⠇⢸⣤⣄⠉⠹⣷⣆⣠⠃⢿⢹⣧⠻⠟⢀⢴')
    line_chars = set(line)
    # If more than 30% of unique chars are banner chars, it's banner
    if line_chars and len(line_chars & banner_chars) / len(line_chars) > 0.3:
        return True
    # Box drawing characters
    if re.match(r'^[╭╮╰╯│─\s]+$', line):
        return True
    return False

def filter_tool_logs(text: str) -> str:
    """Remove verbose tool execution logs from output."""
    lines = text.split('\n')
    filtered = [line for line in lines if not is_tool_log_line(line)]
    result = '\n'.join(filtered)
    # Clean up multiple blank lines
    result = re.sub(r'\n{3,}', '\n\n', result)
    return result


@dataclass
class KiroAgentConfig(AgentConfig):
    """Configuration for Kiro agent."""

    model: str = "claude-sonnet-4.5"  # claude-opus-4.5, claude-sonnet-4.5, claude-haiku-4.5
    trust_all_tools: bool = False  # If True, uses --trust-all-tools (allows writes)
    # Trusted tools for read-only operations (safe to auto-approve)
    trusted_tools: list = None  # Default set in __post_init__

    def __post_init__(self):
        if self.trusted_tools is None:
            # Trust read-only tools by default for non-interactive mode
            # Note: Some tools require @mcpserver/ prefix - using built-in tool names
            self.trusted_tools = [
                "fs_read",
                "web_search",
                "web_fetch",
            ]


class KiroAgent(Agent):
    """Agent that uses kiro-cli for Claude models."""

    def __init__(self, config: KiroAgentConfig) -> None:
        super().__init__(config)
        self._kiro_path = shutil.which("kiro-cli")
        if not self._kiro_path:
            # Check common locations
            import os
            for path in [
                os.path.expanduser("~/.local/bin/kiro-cli"),
                "/usr/local/bin/kiro-cli",
            ]:
                if os.path.exists(path):
                    self._kiro_path = path
                    break

    @property
    def available(self) -> bool:
        """Check if kiro-cli is available."""
        return self._kiro_path is not None

    async def chat(
        self,
        messages: list,
        context: dict[str, Any] | None = None,
    ) -> AsyncIterator[str]:
        """Chat using kiro-cli."""
        if not self.available:
            yield "❌ kiro-cli not found. Install it with:\n"
            yield "```\ncurl -fsSL https://cli.kiro.dev/install | bash\n```\n"
            yield "Then run `kiro-cli login` to authenticate."
            return

        # Build the prompt from messages
        prompt_parts = []
        
        # Add system prompt
        system_prompt = self.get_system_prompt(context)
        if system_prompt:
            prompt_parts.append(f"System: {system_prompt}\n")

        # Add conversation history
        for msg in messages:
            role = msg.role.capitalize()
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            prompt_parts.append(f"{role}: {content}")

        full_prompt = "\n\n".join(prompt_parts)

        # Get model from settings (dynamic) or fall back to config
        from app.config import settings
        model = settings.default_model or self.config.model or "claude-sonnet-4.5"
        
        # Build kiro-cli command
        cmd = [
            self._kiro_path,
            "chat",
            "--no-interactive",
            "--wrap", "never",
        ]

        # Add model
        if model:
            cmd.extend(["--model", model])

        # Add tool trust settings
        if hasattr(self.config, 'trust_all_tools') and self.config.trust_all_tools:
            cmd.append("--trust-all-tools")
        elif hasattr(self.config, 'trusted_tools') and self.config.trusted_tools:
            # Trust only specific tools (read-only by default)
            tools_list = ",".join(self.config.trusted_tools)
            cmd.extend(["--trust-tools", tools_list])

        # Add the prompt
        cmd.append(full_prompt)

        # Run kiro-cli and stream output
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"Running kiro-cli: {' '.join(cmd[:3])}...")  # Log command (not full prompt)

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            # Stream stdout with line-based filtering
            buffer = ""
            total_received = 0
            lines_yielded = 0
            lines_filtered = 0
            in_banner = True  # Start assuming we're in banner

            while True:
                chunk = await process.stdout.read(512)
                if not chunk:
                    # Flush remaining buffer
                    if buffer.strip():
                        buffer = ANSI_ESCAPE.sub('', buffer)
                        cleaned = buffer.strip()
                        # Strip leading > from kiro response
                        if cleaned.startswith('> '):
                            cleaned = cleaned[2:]
                        if cleaned and not is_tool_log_line(cleaned) and not is_kiro_banner_line(cleaned):
                            yield cleaned
                            lines_yielded += 1
                    break

                text = chunk.decode("utf-8", errors="replace")
                buffer += text
                total_received += len(text)

                # Process complete lines only
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    line = ANSI_ESCAPE.sub('', line)
                    cleaned = line.strip()

                    # Skip empty lines at start (banner area)
                    if not cleaned and in_banner:
                        lines_filtered += 1
                        continue

                    # Check for banner content
                    if is_kiro_banner_line(cleaned):
                        lines_filtered += 1
                        continue

                    # Check for tool logs and startup noise
                    if is_tool_log_line(cleaned):
                        lines_filtered += 1
                        continue

                    # Real content found - no longer in banner
                    in_banner = False

                    # Strip leading > from kiro response prefix
                    if cleaned.startswith('> '):
                        cleaned = cleaned[2:]
                        line = cleaned

                    # Yield non-empty content
                    if cleaned:
                        yield line + '\n'
                        lines_yielded += 1
                    else:
                        lines_filtered += 1

            # Wait for completion
            await process.wait()

            logger.info(f"Kiro-cli finished: received={total_received} bytes, yielded={lines_yielded} lines, filtered={lines_filtered} lines, returncode={process.returncode}")

            # Check for errors
            if process.returncode != 0:
                stderr = await process.stderr.read()
                error_text = stderr.decode("utf-8", errors="replace")
                logger.error(f"Kiro-cli error: {error_text}")
                if "login" in error_text.lower() or "auth" in error_text.lower():
                    yield "\n\n❌ Kiro CLI not authenticated. Run `kiro-cli login` first."
                else:
                    yield f"\n\n❌ Kiro CLI error: {error_text}"
            elif total_received == 0:
                logger.warning("Kiro-cli returned no output")
                yield "\n\n⚠️ No response from Kiro. The model may be overloaded or the request timed out."

        except Exception as e:
            logger.exception(f"Kiro-cli exception: {e}")
            yield f"\n\n❌ Error running kiro-cli: {e}"


def create_kiro_agent(
    agent_id: str = "kiro",
    name: str = "Kiro",
    description: str = "Claude via Kiro CLI (AWS-hosted)",
    model: str = "claude-sonnet",
    system_prompt: str = "",
    **kwargs: Any,
) -> KiroAgent:
    """Factory function to create a Kiro agent."""
    config = KiroAgentConfig(
        id=agent_id,
        name=name,
        description=description,
        icon="🦜",
        model=model,
        system_prompt=system_prompt,
        **kwargs,
    )
    return KiroAgent(config)
