"""Command registry for slash commands."""

import re
from dataclasses import dataclass, field
from typing import Callable, Any


@dataclass
class Command:
    """A slash command definition."""

    name: str  # e.g., "review"
    description: str  # Short description for help
    usage: str  # e.g., "/review <file>"
    handler: Callable[[str, dict[str, Any]], dict[str, Any]]  # (args, context) -> result
    examples: list[str] = field(default_factory=list)

    def __post_init__(self):
        # Normalize name
        self.name = self.name.lower().strip()


class CommandRegistry:
    """Registry for slash commands."""

    def __init__(self):
        self._commands: dict[str, Command] = {}

    def register(self, command: Command) -> None:
        """Register a command."""
        self._commands[command.name] = command

    def get(self, name: str) -> Command | None:
        """Get a command by name."""
        return self._commands.get(name.lower())

    def list_all(self) -> list[Command]:
        """List all registered commands."""
        return list(self._commands.values())

    def parse(self, message: str) -> tuple[Command | None, str]:
        """Parse a message for a slash command.

        Returns (command, args) if found, (None, message) otherwise.
        """
        message = message.strip()
        if not message.startswith("/"):
            return None, message

        # Parse: /command args...
        match = re.match(r'^/(\w+)\s*(.*)', message, re.DOTALL)
        if not match:
            return None, message

        cmd_name = match.group(1).lower()
        args = match.group(2).strip()

        command = self.get(cmd_name)
        return command, args

    def get_help(self) -> str:
        """Get help text for all commands."""
        lines = ["## Available Commands\n"]
        for cmd in sorted(self._commands.values(), key=lambda c: c.name):
            lines.append(f"**{cmd.usage}**")
            lines.append(f"  {cmd.description}")
            if cmd.examples:
                lines.append(f"  Examples: {', '.join(cmd.examples)}")
            lines.append("")
        return "\n".join(lines)


# Global registry
command_registry = CommandRegistry()
