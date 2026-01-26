"""Slash commands for quick actions."""

from app.commands.registry import command_registry, Command
from app.commands.handlers import register_default_commands

# Register default commands on import
register_default_commands()

__all__ = ["command_registry", "Command"]
