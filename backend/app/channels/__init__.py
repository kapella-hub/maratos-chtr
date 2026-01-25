"""Channel integrations for MaratOS."""

from app.channels.base import Channel, ChannelMessage
from app.channels.telegram import TelegramChannel
from app.channels.imessage import IMessageChannel
from app.channels.webex import WebexChannel

__all__ = [
    "Channel",
    "ChannelMessage", 
    "TelegramChannel",
    "IMessageChannel",
    "WebexChannel",
]
