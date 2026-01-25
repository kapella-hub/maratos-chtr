"""Channel manager for coordinating all messaging integrations."""

import logging
from typing import Any

from app.agents import agent_registry
from app.agents.base import Message
from app.channels.base import Channel, ChannelMessage, ChannelResponse
from app.channels.telegram import TelegramChannel
from app.channels.imessage import IMessageChannel
from app.channels.webex import WebexChannel

logger = logging.getLogger(__name__)


class ChannelManager:
    """Manages all messaging channel integrations."""
    
    def __init__(self) -> None:
        self._channels: dict[str, Channel] = {}
        self._sessions: dict[str, list[Message]] = {}  # chat_id -> conversation history
    
    def register(self, channel: Channel) -> None:
        """Register a channel."""
        channel.set_handler(self._handle_message)
        self._channels[channel.name] = channel
        logger.info(f"Registered channel: {channel.name}")
    
    def get(self, name: str) -> Channel | None:
        """Get a channel by name."""
        return self._channels.get(name)
    
    def list_channels(self) -> list[dict[str, Any]]:
        """List all channels with status."""
        return [ch.get_status() for ch in self._channels.values()]
    
    async def start_all(self) -> None:
        """Start all enabled channels."""
        for channel in self._channels.values():
            if channel.enabled:
                try:
                    await channel.start()
                except Exception as e:
                    logger.error(f"Failed to start {channel.name}: {e}")
    
    async def stop_all(self) -> None:
        """Stop all channels."""
        for channel in self._channels.values():
            try:
                await channel.stop()
            except Exception as e:
                logger.error(f"Failed to stop {channel.name}: {e}")
    
    async def _handle_message(self, msg: ChannelMessage) -> ChannelResponse | None:
        """Handle an incoming message from any channel."""
        logger.info(f"[{msg.channel}] {msg.sender_name}: {msg.text[:50]}...")
        
        # Get or create conversation history for this chat
        session_key = f"{msg.channel}:{msg.chat_id or msg.sender_id}"
        if session_key not in self._sessions:
            self._sessions[session_key] = []
        
        history = self._sessions[session_key]
        
        # Add user message to history
        history.append(Message(role="user", content=msg.text))
        
        # Keep history reasonable (last 20 messages)
        if len(history) > 20:
            history = history[-20:]
            self._sessions[session_key] = history
        
        # Get MO's response
        agent = agent_registry.get_default()
        
        context = {
            "channel": msg.channel,
            "sender": msg.sender_name or msg.sender_id,
            "chat": msg.chat_name or msg.chat_id,
        }
        
        try:
            # Collect full response (no streaming for channels)
            response_text = ""
            async for chunk in agent.chat(history, context):
                response_text += chunk
            
            # Add assistant message to history
            history.append(Message(role="assistant", content=response_text))
            
            return ChannelResponse(text=response_text)
            
        except Exception as e:
            logger.error(f"Error handling message: {e}")
            return ChannelResponse(text=f"Sorry, I encountered an error: {str(e)[:100]}")
    
    def clear_session(self, channel: str, chat_id: str) -> None:
        """Clear conversation history for a chat."""
        session_key = f"{channel}:{chat_id}"
        if session_key in self._sessions:
            del self._sessions[session_key]


# Global channel manager
channel_manager = ChannelManager()


def init_channels(config: dict[str, Any]) -> None:
    """Initialize channels from config."""
    
    # Telegram
    if "telegram" in config:
        channel_manager.register(TelegramChannel(config["telegram"]))
    
    # iMessage
    if "imessage" in config:
        channel_manager.register(IMessageChannel(config["imessage"]))
    
    # Webex
    if "webex" in config:
        channel_manager.register(WebexChannel(config["webex"]))
