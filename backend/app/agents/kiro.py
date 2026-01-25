"""Kiro CLI agent - uses kiro-cli for Claude models via AWS."""

import asyncio
import re
import shutil
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from app.agents.base import Agent, AgentConfig

# Regex to strip ANSI escape codes
ANSI_ESCAPE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')


@dataclass
class KiroAgentConfig(AgentConfig):
    """Configuration for Kiro agent."""

    model: str = "claude-sonnet-4"  # claude-opus-4.5, claude-sonnet-4, claude-sonnet-4.5, claude-haiku-4.5
    trust_tools: bool = True  # --trust-all-tools flag


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

        # Build kiro-cli command
        cmd = [
            self._kiro_path,
            "chat",
            "--no-interactive",
            "--wrap", "never",
        ]

        # Add model if specified
        if hasattr(self.config, 'model') and self.config.model:
            cmd.extend(["--model", self.config.model])

        # Add trust-all-tools if enabled
        if hasattr(self.config, 'trust_tools') and self.config.trust_tools:
            cmd.append("--trust-all-tools")

        # Add the prompt
        cmd.append(full_prompt)

        # Run kiro-cli and stream output
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            # Stream stdout
            while True:
                chunk = await process.stdout.read(100)
                if not chunk:
                    break
                text = chunk.decode("utf-8", errors="replace")
                # Strip ANSI escape codes from terminal output
                text = ANSI_ESCAPE.sub('', text)
                yield text

            # Wait for completion
            await process.wait()

            # Check for errors
            if process.returncode != 0:
                stderr = await process.stderr.read()
                error_text = stderr.decode("utf-8", errors="replace")
                if "login" in error_text.lower() or "auth" in error_text.lower():
                    yield "\n\n❌ Kiro CLI not authenticated. Run `kiro-cli login` first."
                else:
                    yield f"\n\n❌ Kiro CLI error: {error_text}"

        except Exception as e:
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
