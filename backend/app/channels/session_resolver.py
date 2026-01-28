"""Session resolver for unified channel message handling.

Resolves external channel messages to internal sessions, creating new sessions
when needed and maintaining the channel-to-session mapping.
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import (
    ChannelThreadMapping,
    Message as DBMessage,
    Session as DBSession,
)

logger = logging.getLogger(__name__)


@dataclass
class MessageEnvelope:
    """Normalized message envelope for all channels.

    This is the canonical format for incoming messages from any channel,
    providing a consistent interface for session resolution and persistence.
    """

    # Channel identification
    channel_type: str  # telegram, imessage, webex
    external_thread_id: str  # Platform-specific chat/thread ID
    external_message_id: str  # Platform-specific message ID

    # Sender info
    sender_id: str
    sender_name: str | None = None

    # Content
    text: str = ""
    attachments: list[dict] = field(default_factory=list)

    # Metadata
    timestamp: datetime = field(default_factory=datetime.now)
    reply_to_id: str | None = None
    raw_data: dict = field(default_factory=dict)

    @classmethod
    def from_channel_message(cls, msg: "ChannelMessage") -> "MessageEnvelope":
        """Create envelope from ChannelMessage."""
        from app.channels.base import ChannelMessage

        return cls(
            channel_type=msg.channel,
            external_thread_id=msg.chat_id or msg.sender_id,
            external_message_id=msg.id,
            sender_id=msg.sender_id,
            sender_name=msg.sender_name,
            text=msg.text,
            attachments=msg.attachments,
            timestamp=msg.timestamp,
            reply_to_id=msg.reply_to,
            raw_data=msg.raw,
        )


@dataclass
class ResolvedSession:
    """Result of session resolution."""

    session_id: str
    is_new: bool  # True if session was just created
    channel_type: str
    external_thread_id: str


class SessionResolver:
    """Resolves channel messages to internal sessions.

    Maintains mapping between external channel threads and internal sessions.
    Creates new sessions when a thread is seen for the first time.
    """

    async def resolve_or_create(
        self,
        db: AsyncSession,
        envelope: MessageEnvelope,
    ) -> ResolvedSession:
        """Resolve an external channel thread to an internal session.

        If a session exists for this channel+thread, returns it.
        Otherwise, creates a new session and mapping.

        Args:
            db: Database session
            envelope: Normalized message envelope

        Returns:
            ResolvedSession with session_id and whether it's new
        """
        # Look for existing mapping
        result = await db.execute(
            select(ChannelThreadMapping).where(
                ChannelThreadMapping.channel_type == envelope.channel_type,
                ChannelThreadMapping.external_thread_id == envelope.external_thread_id,
            )
        )
        mapping = result.scalar_one_or_none()

        if mapping:
            # Update last_message_at
            await db.execute(
                update(ChannelThreadMapping)
                .where(ChannelThreadMapping.id == mapping.id)
                .values(last_message_at=datetime.utcnow())
            )

            return ResolvedSession(
                session_id=mapping.session_id,
                is_new=False,
                channel_type=envelope.channel_type,
                external_thread_id=envelope.external_thread_id,
            )

        # Create new session
        session_id = str(uuid.uuid4())
        title = self._generate_title(envelope)

        new_session = DBSession(
            id=session_id,
            agent_id="mo",  # Default to MO agent
            title=title,
            channel_type=envelope.channel_type,
            external_thread_id=envelope.external_thread_id,
            channel_user_id=envelope.sender_id,
            channel_user_name=envelope.sender_name,
        )
        db.add(new_session)

        # Create mapping
        new_mapping = ChannelThreadMapping(
            channel_type=envelope.channel_type,
            external_thread_id=envelope.external_thread_id,
            session_id=session_id,
            channel_user_id=envelope.sender_id,
            channel_user_name=envelope.sender_name,
        )
        db.add(new_mapping)

        await db.flush()  # Ensure IDs are assigned

        logger.info(
            f"Created new session {session_id} for {envelope.channel_type}:{envelope.external_thread_id}"
        )

        return ResolvedSession(
            session_id=session_id,
            is_new=True,
            channel_type=envelope.channel_type,
            external_thread_id=envelope.external_thread_id,
        )

    async def get_session_history(
        self,
        db: AsyncSession,
        session_id: str,
        limit: int = 50,
    ) -> list[DBMessage]:
        """Get message history for a session.

        Args:
            db: Database session
            session_id: Session ID
            limit: Maximum number of messages to return (most recent N messages)

        Returns:
            List of messages ordered chronologically (oldest first)
        """
        # For small histories, just get all messages in order
        # For large histories, we'd need a subquery to get most recent N then re-sort
        result = await db.execute(
            select(DBMessage)
            .where(DBMessage.session_id == session_id)
            .order_by(DBMessage.created_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def persist_message(
        self,
        db: AsyncSession,
        session_id: str,
        role: str,
        content: str,
        envelope: MessageEnvelope | None = None,
        thinking_data: str | None = None,
        tool_calls: dict | None = None,
    ) -> DBMessage:
        """Persist a message to the database.

        Args:
            db: Database session
            session_id: Session ID
            role: Message role (user, assistant, system, tool)
            content: Message content
            envelope: Original message envelope (for user messages)
            thinking_data: Thinking blocks JSON (for assistant messages)
            tool_calls: Tool calls JSON (for assistant messages)

        Returns:
            Created message record
        """
        message_id = str(uuid.uuid4())

        message = DBMessage(
            id=message_id,
            session_id=session_id,
            role=role,
            content=content,
            thinking_data=thinking_data,
            tool_calls=tool_calls,
            source_channel=envelope.channel_type if envelope else "web",
            external_message_id=envelope.external_message_id if envelope else None,
            sender_id=envelope.sender_id if envelope else None,
            sender_name=envelope.sender_name if envelope else None,
            attachments=envelope.attachments if envelope else None,
        )
        db.add(message)
        await db.flush()

        return message

    async def find_session_by_channel(
        self,
        db: AsyncSession,
        channel_type: str,
        external_thread_id: str,
    ) -> DBSession | None:
        """Find a session by channel and thread ID.

        Args:
            db: Database session
            channel_type: Channel type (telegram, imessage, webex)
            external_thread_id: External thread/chat ID

        Returns:
            Session if found, None otherwise
        """
        result = await db.execute(
            select(ChannelThreadMapping).where(
                ChannelThreadMapping.channel_type == channel_type,
                ChannelThreadMapping.external_thread_id == external_thread_id,
            )
        )
        mapping = result.scalar_one_or_none()

        if not mapping:
            return None

        result = await db.execute(
            select(DBSession).where(DBSession.id == mapping.session_id)
        )
        return result.scalar_one_or_none()

    async def list_channel_sessions(
        self,
        db: AsyncSession,
        channel_type: str | None = None,
        limit: int = 50,
    ) -> list[DBSession]:
        """List sessions, optionally filtered by channel type.

        Args:
            db: Database session
            channel_type: Filter by channel type (None for all)
            limit: Maximum number of sessions

        Returns:
            List of sessions ordered by updated_at descending
        """
        query = select(DBSession).order_by(DBSession.updated_at.desc()).limit(limit)

        if channel_type:
            query = query.where(DBSession.channel_type == channel_type)

        result = await db.execute(query)
        return list(result.scalars().all())

    def _generate_title(self, envelope: MessageEnvelope) -> str:
        """Generate a title for a new session.

        Args:
            envelope: Message envelope

        Returns:
            Session title
        """
        channel_display = {
            "telegram": "Telegram",
            "imessage": "iMessage",
            "webex": "Webex",
        }.get(envelope.channel_type, envelope.channel_type.title())

        if envelope.sender_name:
            return f"{channel_display}: {envelope.sender_name}"
        else:
            return f"{channel_display} Chat"


# Global resolver instance
session_resolver = SessionResolver()
