"""Base channel interface for messaging integrations."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Coroutine


@dataclass
class ChannelMessage:
    """Incoming message from a channel."""
    
    id: str
    channel: str  # telegram, imessage, webex
    sender_id: str
    sender_name: str | None = None
    text: str = ""
    attachments: list[dict] = field(default_factory=list)
    chat_id: str | None = None  # For group chats
    chat_name: str | None = None
    reply_to: str | None = None
    timestamp: datetime = field(default_factory=datetime.now)
    raw: dict = field(default_factory=dict)


@dataclass 
class ChannelResponse:
    """Response to send back to channel."""
    
    text: str
    attachments: list[dict] = field(default_factory=list)
    reply_to: str | None = None
    parse_mode: str | None = None  # markdown, html


# Type for message handler callback
MessageHandler = Callable[[ChannelMessage], Coroutine[Any, Any, ChannelResponse | None]]


class Channel(ABC):
    """Base class for messaging channel integrations."""
    
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.enabled = config.get("enabled", True)
        self._handler: MessageHandler | None = None
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Channel identifier (telegram, imessage, webex)."""
        pass
    
    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable channel name."""
        pass
    
    def set_handler(self, handler: MessageHandler) -> None:
        """Set the message handler callback."""
        self._handler = handler
    
    @abstractmethod
    async def start(self) -> None:
        """Start the channel (connect, start polling, etc)."""
        pass
    
    @abstractmethod
    async def stop(self) -> None:
        """Stop the channel gracefully."""
        pass
    
    @abstractmethod
    async def send(self, chat_id: str, response: ChannelResponse) -> bool:
        """Send a message to a specific chat."""
        pass
    
    async def handle_message(self, message: ChannelMessage) -> None:
        """Process an incoming message."""
        if self._handler:
            response = await self._handler(message)
            if response:
                await self.send(message.chat_id or message.sender_id, response)
    
    def get_status(self) -> dict[str, Any]:
        """Get channel status."""
        return {
            "name": self.name,
            "display_name": self.display_name,
            "enabled": self.enabled,
        }
