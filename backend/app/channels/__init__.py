"""Channel integrations for MaratOS.

Provides unified session handling across web UI and external channels
(Telegram, iMessage, Webex).
"""

from app.channels.base import Channel, ChannelMessage, ChannelResponse
from app.channels.manager import ChannelManager, channel_manager, init_channels
from app.channels.session_resolver import (
    MessageEnvelope,
    ResolvedSession,
    SessionResolver,
    session_resolver,
)
from app.channels.redaction import (
    RedactionPattern,
    apply_redaction_hooks,
    apply_post_hooks,
    register_pattern,
    register_pre_hook,
    register_post_hook,
    enable_pattern,
    disable_pattern,
)
from app.channels.telegram import TelegramChannel
from app.channels.imessage import IMessageChannel
from app.channels.webex import WebexChannel

__all__ = [
    # Base types
    "Channel",
    "ChannelMessage",
    "ChannelResponse",
    # Manager
    "ChannelManager",
    "channel_manager",
    "init_channels",
    # Session resolution
    "MessageEnvelope",
    "ResolvedSession",
    "SessionResolver",
    "session_resolver",
    # Redaction
    "RedactionPattern",
    "apply_redaction_hooks",
    "apply_post_hooks",
    "register_pattern",
    "register_pre_hook",
    "register_post_hook",
    "enable_pattern",
    "disable_pattern",
    # Channel implementations
    "TelegramChannel",
    "IMessageChannel",
    "WebexChannel",
]
