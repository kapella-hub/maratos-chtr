"""Channel manager for coordinating all messaging integrations.

Manages channel lifecycle and routes messages through the unified session store.
"""

import logging
from typing import Any

from app.agents import agent_registry
from app.agents.base import Message
from app.channels.base import Channel, ChannelMessage, ChannelResponse
from app.channels.session_resolver import MessageEnvelope, session_resolver
from app.channels.redaction import apply_redaction_hooks
from app.database import async_session_factory

logger = logging.getLogger(__name__)


class ChannelManager:
    """Manages all messaging channel integrations.

    Routes incoming channel messages through:
    1. Session resolution (find or create DB session)
    2. Message persistence (store user message)
    3. Agent processing (get response)
    4. Response persistence (store assistant message)
    5. Channel response (send back to platform)
    """

    def __init__(self) -> None:
        self._channels: dict[str, Channel] = {}

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
        """Handle an incoming message from any channel.

        Routes through unified session store for persistence.
        """
        logger.info(f"[{msg.channel}] {msg.sender_name}: {msg.text[:50]}...")

        # Create message envelope
        envelope = MessageEnvelope.from_channel_message(msg)

        async with async_session_factory() as db:
            try:
                # Resolve or create session
                resolved = await session_resolver.resolve_or_create(db, envelope)

                if resolved.is_new:
                    logger.info(
                        f"New session {resolved.session_id} created for "
                        f"{envelope.channel_type}:{envelope.external_thread_id}"
                    )

                # Apply pre-persist redaction hooks
                redacted_text, was_redacted = apply_redaction_hooks(envelope.text)
                envelope.text = redacted_text

                # Persist user message
                await session_resolver.persist_message(
                    db=db,
                    session_id=resolved.session_id,
                    role="user",
                    content=envelope.text,
                    envelope=envelope,
                )

                # Mark message as redacted if needed
                if was_redacted:
                    logger.info(f"Message content was redacted for session {resolved.session_id}")

                # Get conversation history for agent context
                history_messages = await session_resolver.get_session_history(
                    db=db,
                    session_id=resolved.session_id,
                    limit=50,
                )

                # Convert to agent Message format
                history = [
                    Message(role=m.role, content=m.content)
                    for m in history_messages
                ]

                # Get agent (default to MO)
                agent = agent_registry.get_default()

                context = {
                    "channel": msg.channel,
                    "sender": msg.sender_name or msg.sender_id,
                    "chat": msg.chat_name or msg.chat_id,
                    "session_id": resolved.session_id,
                }

                # Collect full response (no streaming for channels)
                response_text = ""
                async for chunk in agent.chat(history, context):
                    response_text += chunk

                # Persist assistant message
                await session_resolver.persist_message(
                    db=db,
                    session_id=resolved.session_id,
                    role="assistant",
                    content=response_text,
                )

                # Commit all changes
                await db.commit()

                return ChannelResponse(text=response_text)

            except Exception as e:
                logger.error(f"Error handling message: {e}", exc_info=True)
                await db.rollback()
                return ChannelResponse(
                    text=f"Sorry, I encountered an error: {str(e)[:100]}"
                )

    async def clear_session(self, channel: str, chat_id: str) -> bool:
        """Clear conversation history for a chat.

        Note: This doesn't delete DB records, but could be extended to
        soft-delete or archive messages.

        Args:
            channel: Channel name
            chat_id: External chat/thread ID

        Returns:
            True if session was found and cleared
        """
        async with async_session_factory() as db:
            session = await session_resolver.find_session_by_channel(
                db=db,
                channel_type=channel,
                external_thread_id=chat_id,
            )

            if session:
                logger.info(f"Session {session.id} found for {channel}:{chat_id}")
                # For now, just log. Could implement soft-delete later.
                return True

            return False


# Global channel manager
channel_manager = ChannelManager()


def init_channels(config: dict[str, Any]) -> None:
    """Initialize channels from config."""
    # Import here to avoid circular imports
    from app.channels.telegram import TelegramChannel
    from app.channels.imessage import IMessageChannel
    from app.channels.webex import WebexChannel

    # Telegram
    if "telegram" in config:
        channel_manager.register(TelegramChannel(config["telegram"]))

    # iMessage
    if "imessage" in config:
        channel_manager.register(IMessageChannel(config["imessage"]))

    # Webex
    if "webex" in config:
        channel_manager.register(WebexChannel(config["webex"]))
