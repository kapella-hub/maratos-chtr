"""Tests for unified channel/session handling.

Tests:
- Channel message creates session
- Messages persist and can be retrieved
- Session resolution finds existing session
- New thread creates new session
- Redaction hooks work
- Web UI can filter by channel_type
"""

import asyncio
import os
import pytest
import pytest_asyncio
import tempfile
from datetime import datetime
from pathlib import Path
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Set up test database URL before importing app modules
os.environ["MARATOS_DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

from app.database import (
    Base,
    ChannelThreadMapping,
    Message as DBMessage,
    Session as DBSession,
)
from app.channels.session_resolver import (
    MessageEnvelope,
    SessionResolver,
)
from app.channels.redaction import (
    apply_redaction_hooks,
    apply_patterns,
    register_pre_hook,
    register_post_hook,
    apply_post_hooks,
    clear_hooks,
    reset_patterns,
    enable_pattern,
    disable_pattern,
)


@pytest_asyncio.fixture
async def db_factory():
    """Create a fresh test database session factory for each test."""
    tmpdir = tempfile.mkdtemp()
    db_path = Path(tmpdir) / "test.db"
    db_url = f"sqlite+aiosqlite:///{db_path}"

    # Create engine and tables
    engine = create_async_engine(
        db_url,
        connect_args={"check_same_thread": False},
        echo=False,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Create session factory
    factory = async_sessionmaker(engine, expire_on_commit=False)

    yield factory

    await engine.dispose()


class TestMessageEnvelope:
    """Tests for MessageEnvelope model."""

    def test_create_envelope(self):
        """Test creating a message envelope."""
        envelope = MessageEnvelope(
            channel_type="telegram",
            external_thread_id="chat123",
            external_message_id="msg456",
            sender_id="user789",
            sender_name="John Doe",
            text="Hello, world!",
            attachments=[{"type": "photo", "url": "http://example.com/photo.jpg"}],
        )

        assert envelope.channel_type == "telegram"
        assert envelope.external_thread_id == "chat123"
        assert envelope.external_message_id == "msg456"
        assert envelope.sender_id == "user789"
        assert envelope.sender_name == "John Doe"
        assert envelope.text == "Hello, world!"
        assert len(envelope.attachments) == 1

    def test_envelope_from_channel_message(self):
        """Test creating envelope from ChannelMessage."""
        from app.channels.base import ChannelMessage

        msg = ChannelMessage(
            id="msg123",
            channel="telegram",
            sender_id="user456",
            sender_name="Jane Doe",
            text="Test message",
            chat_id="chat789",
            attachments=[],
        )

        envelope = MessageEnvelope.from_channel_message(msg)

        assert envelope.channel_type == "telegram"
        assert envelope.external_thread_id == "chat789"
        assert envelope.external_message_id == "msg123"
        assert envelope.sender_id == "user456"
        assert envelope.sender_name == "Jane Doe"
        assert envelope.text == "Test message"

    def test_envelope_uses_sender_id_as_thread_if_no_chat_id(self):
        """Test that envelope uses sender_id as thread ID when chat_id is None."""
        from app.channels.base import ChannelMessage

        msg = ChannelMessage(
            id="msg123",
            channel="imessage",
            sender_id="user456",
            text="Direct message",
            chat_id=None,
        )

        envelope = MessageEnvelope.from_channel_message(msg)

        assert envelope.external_thread_id == "user456"


class TestSessionResolver:
    """Tests for session resolution logic."""

    @pytest.mark.asyncio
    async def test_creates_new_session_for_new_thread(self, db_factory):
        """Test that a new session is created for an unknown thread."""
        resolver = SessionResolver()

        async with db_factory() as db:
            envelope = MessageEnvelope(
                channel_type="telegram",
                external_thread_id="new_chat_123",
                external_message_id="msg1",
                sender_id="user1",
                sender_name="Test User",
                text="Hello",
            )

            resolved = await resolver.resolve_or_create(db, envelope)
            await db.commit()

            assert resolved.is_new is True
            assert resolved.session_id is not None
            assert resolved.channel_type == "telegram"
            assert resolved.external_thread_id == "new_chat_123"

            # Verify session was created
            result = await db.execute(
                select(DBSession).where(DBSession.id == resolved.session_id)
            )
            session = result.scalar_one()

            assert session.channel_type == "telegram"
            assert session.external_thread_id == "new_chat_123"
            assert session.channel_user_id == "user1"
            assert session.channel_user_name == "Test User"

    @pytest.mark.asyncio
    async def test_finds_existing_session_for_known_thread(self, db_factory):
        """Test that an existing session is returned for a known thread."""
        resolver = SessionResolver()

        async with db_factory() as db:
            envelope = MessageEnvelope(
                channel_type="webex",
                external_thread_id="existing_chat",
                external_message_id="msg1",
                sender_id="user1",
                text="First message",
            )

            # First resolution creates session
            first_resolved = await resolver.resolve_or_create(db, envelope)
            await db.commit()

            assert first_resolved.is_new is True

            # Second resolution should find existing
            envelope2 = MessageEnvelope(
                channel_type="webex",
                external_thread_id="existing_chat",
                external_message_id="msg2",
                sender_id="user1",
                text="Second message",
            )

            second_resolved = await resolver.resolve_or_create(db, envelope2)
            await db.commit()

            assert second_resolved.is_new is False
            assert second_resolved.session_id == first_resolved.session_id

    @pytest.mark.asyncio
    async def test_different_threads_get_different_sessions(self, db_factory):
        """Test that different threads get different sessions."""
        resolver = SessionResolver()

        async with db_factory() as db:
            envelope1 = MessageEnvelope(
                channel_type="telegram",
                external_thread_id="chat1",
                external_message_id="msg1",
                sender_id="user1",
                text="Thread 1",
            )

            envelope2 = MessageEnvelope(
                channel_type="telegram",
                external_thread_id="chat2",
                external_message_id="msg2",
                sender_id="user1",
                text="Thread 2",
            )

            resolved1 = await resolver.resolve_or_create(db, envelope1)
            resolved2 = await resolver.resolve_or_create(db, envelope2)
            await db.commit()

            assert resolved1.session_id != resolved2.session_id
            assert resolved1.is_new is True
            assert resolved2.is_new is True

    @pytest.mark.asyncio
    async def test_same_thread_different_channels_get_different_sessions(self, db_factory):
        """Test that same thread ID on different channels gets different sessions."""
        resolver = SessionResolver()

        async with db_factory() as db:
            envelope_telegram = MessageEnvelope(
                channel_type="telegram",
                external_thread_id="12345",
                external_message_id="msg1",
                sender_id="user1",
                text="Telegram message",
            )

            envelope_webex = MessageEnvelope(
                channel_type="webex",
                external_thread_id="12345",
                external_message_id="msg2",
                sender_id="user1",
                text="Webex message",
            )

            resolved_telegram = await resolver.resolve_or_create(db, envelope_telegram)
            resolved_webex = await resolver.resolve_or_create(db, envelope_webex)
            await db.commit()

            assert resolved_telegram.session_id != resolved_webex.session_id


class TestMessagePersistence:
    """Tests for message persistence."""

    @pytest.mark.asyncio
    async def test_persist_user_message(self, db_factory):
        """Test persisting a user message with envelope."""
        resolver = SessionResolver()

        async with db_factory() as db:
            envelope = MessageEnvelope(
                channel_type="telegram",
                external_thread_id="chat123",
                external_message_id="msg456",
                sender_id="user789",
                sender_name="John",
                text="Test message",
                attachments=[{"type": "photo"}],
            )

            resolved = await resolver.resolve_or_create(db, envelope)

            message = await resolver.persist_message(
                db=db,
                session_id=resolved.session_id,
                role="user",
                content=envelope.text,
                envelope=envelope,
            )
            await db.commit()

            assert message.id is not None
            assert message.session_id == resolved.session_id
            assert message.role == "user"
            assert message.content == "Test message"
            assert message.source_channel == "telegram"
            assert message.external_message_id == "msg456"
            assert message.sender_id == "user789"
            assert message.sender_name == "John"
            assert message.attachments == [{"type": "photo"}]

    @pytest.mark.asyncio
    async def test_persist_assistant_message(self, db_factory):
        """Test persisting an assistant message."""
        resolver = SessionResolver()

        async with db_factory() as db:
            envelope = MessageEnvelope(
                channel_type="telegram",
                external_thread_id="chat123",
                external_message_id="msg1",
                sender_id="user1",
                text="User message",
            )

            resolved = await resolver.resolve_or_create(db, envelope)

            message = await resolver.persist_message(
                db=db,
                session_id=resolved.session_id,
                role="assistant",
                content="Assistant response",
                thinking_data='{"blocks": []}',
            )
            await db.commit()

            assert message.role == "assistant"
            assert message.content == "Assistant response"
            assert message.source_channel == "web"  # Default for non-envelope messages
            assert message.thinking_data == '{"blocks": []}'

    @pytest.mark.asyncio
    async def test_get_session_history(self, db_factory):
        """Test retrieving session history."""
        resolver = SessionResolver()

        async with db_factory() as db:
            envelope = MessageEnvelope(
                channel_type="imessage",
                external_thread_id="thread1",
                external_message_id="msg1",
                sender_id="user1",
                text="First message",
            )

            resolved = await resolver.resolve_or_create(db, envelope)

            # Add multiple messages
            await resolver.persist_message(
                db=db,
                session_id=resolved.session_id,
                role="user",
                content="Message 1",
                envelope=envelope,
            )
            await resolver.persist_message(
                db=db,
                session_id=resolved.session_id,
                role="assistant",
                content="Response 1",
            )
            await resolver.persist_message(
                db=db,
                session_id=resolved.session_id,
                role="user",
                content="Message 2",
                envelope=envelope,
            )
            await db.commit()

            # Get history
            history = await resolver.get_session_history(
                db=db,
                session_id=resolved.session_id,
            )

            assert len(history) == 3
            assert history[0].content == "Message 1"
            assert history[1].content == "Response 1"
            assert history[2].content == "Message 2"


class TestChannelSessionFiltering:
    """Tests for filtering sessions by channel."""

    @pytest.mark.asyncio
    async def test_list_sessions_by_channel(self, db_factory):
        """Test listing sessions filtered by channel type."""
        resolver = SessionResolver()

        async with db_factory() as db:
            # Create sessions for different channels
            for channel, count in [("telegram", 3), ("imessage", 2), ("webex", 1)]:
                for i in range(count):
                    envelope = MessageEnvelope(
                        channel_type=channel,
                        external_thread_id=f"{channel}_thread_{i}",
                        external_message_id=f"msg_{i}",
                        sender_id=f"user_{i}",
                        text="Test",
                    )
                    await resolver.resolve_or_create(db, envelope)
            await db.commit()

            # Filter by Telegram
            telegram_sessions = await resolver.list_channel_sessions(
                db=db,
                channel_type="telegram",
            )
            assert len(telegram_sessions) == 3

            # Filter by iMessage
            imessage_sessions = await resolver.list_channel_sessions(
                db=db,
                channel_type="imessage",
            )
            assert len(imessage_sessions) == 2

            # Get all
            all_sessions = await resolver.list_channel_sessions(
                db=db,
                channel_type=None,
            )
            assert len(all_sessions) == 6


class TestRedactionHooks:
    """Tests for message redaction."""

    def setup_method(self):
        """Reset hooks before each test."""
        clear_hooks()
        reset_patterns()

    def test_redacts_credit_card_numbers(self):
        """Test that credit card numbers are redacted."""
        text = "My card is 4111-1111-1111-1111"
        result, was_redacted = apply_patterns(text)

        assert "[REDACTED-CC]" in result
        assert "4111" not in result
        assert was_redacted is True

    def test_redacts_ssn(self):
        """Test that SSNs are redacted."""
        text = "My SSN is 123-45-6789"
        result, was_redacted = apply_patterns(text)

        assert "[REDACTED-SSN]" in result
        assert "123-45-6789" not in result
        assert was_redacted is True

    def test_redacts_api_keys(self):
        """Test that API keys are redacted."""
        # Using sk_test_ prefix to avoid GitHub secret scanning false positives
        text = "Use key sk_test_FAKE_not_real_key_12345"
        result, was_redacted = apply_patterns(text)

        assert "[REDACTED-KEY]" in result
        assert "sk_test" not in result
        assert was_redacted is True

    def test_redacts_bearer_tokens(self):
        """Test that bearer tokens are redacted."""
        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
        result, was_redacted = apply_patterns(text)

        assert "Bearer [REDACTED-TOKEN]" in result
        assert was_redacted is True

    def test_redacts_aws_keys(self):
        """Test that AWS keys are redacted."""
        text = "AWS Key: AKIAIOSFODNN7EXAMPLE"
        result, was_redacted = apply_patterns(text)

        assert "[REDACTED-AWS-KEY]" in result
        assert "AKIA" not in result
        assert was_redacted is True

    def test_email_disabled_by_default(self):
        """Test that email redaction is disabled by default."""
        text = "Email me at test@example.com"
        result, was_redacted = apply_patterns(text)

        assert "test@example.com" in result
        assert was_redacted is False

    def test_enable_email_redaction(self):
        """Test enabling email redaction."""
        enable_pattern("email")

        text = "Email me at test@example.com"
        result, was_redacted = apply_patterns(text)

        assert "[REDACTED-EMAIL]" in result
        assert "test@example.com" not in result
        assert was_redacted is True

        disable_pattern("email")

    def test_disable_pattern(self):
        """Test disabling a pattern."""
        disable_pattern("credit_card")

        text = "My card is 4111-1111-1111-1111"
        result, was_redacted = apply_patterns(text)

        assert "4111" in result
        assert was_redacted is False

        enable_pattern("credit_card")

    def test_custom_pre_hook(self):
        """Test custom pre-persist hook."""
        def custom_hook(text: str) -> tuple[str, bool]:
            if "secret" in text.lower():
                return text.replace("secret", "[FILTERED]"), True
            return text, False

        register_pre_hook(custom_hook)

        text = "The secret code is 12345"
        result, was_redacted = apply_redaction_hooks(text)

        assert "[FILTERED]" in result
        assert "secret" not in result
        assert was_redacted is True

    def test_custom_post_hook(self):
        """Test custom post-retrieve hook."""
        def mask_hook(text: str) -> str:
            return text.replace("internal", "[MASKED]")

        register_post_hook(mask_hook)

        text = "This is internal information"
        result = apply_post_hooks(text)

        assert "[MASKED]" in result
        assert "internal" not in result

    def test_multiple_redactions(self):
        """Test multiple patterns applied to same text."""
        text = "Card: 4111-1111-1111-1111, SSN: 123-45-6789"
        result, was_redacted = apply_patterns(text)

        assert "[REDACTED-CC]" in result
        assert "[REDACTED-SSN]" in result
        assert "4111" not in result
        assert "123-45" not in result
        assert was_redacted is True


class TestChannelThreadMapping:
    """Tests for channel-to-session mapping."""

    @pytest.mark.asyncio
    async def test_mapping_unique_constraint(self, db_factory):
        """Test that channel+thread combination is unique."""
        resolver = SessionResolver()

        async with db_factory() as db:
            envelope = MessageEnvelope(
                channel_type="telegram",
                external_thread_id="unique_chat",
                external_message_id="msg1",
                sender_id="user1",
                text="Test",
            )

            await resolver.resolve_or_create(db, envelope)
            await db.commit()

            # Verify mapping exists
            result = await db.execute(
                select(ChannelThreadMapping).where(
                    ChannelThreadMapping.channel_type == "telegram",
                    ChannelThreadMapping.external_thread_id == "unique_chat",
                )
            )
            mappings = list(result.scalars().all())
            assert len(mappings) == 1

    @pytest.mark.asyncio
    async def test_find_session_by_channel(self, db_factory):
        """Test finding a session by channel and thread ID."""
        resolver = SessionResolver()

        async with db_factory() as db:
            envelope = MessageEnvelope(
                channel_type="webex",
                external_thread_id="findable_chat",
                external_message_id="msg1",
                sender_id="user1",
                sender_name="Test User",
                text="Test",
            )

            resolved = await resolver.resolve_or_create(db, envelope)
            await db.commit()

            # Find the session
            found = await resolver.find_session_by_channel(
                db=db,
                channel_type="webex",
                external_thread_id="findable_chat",
            )

            assert found is not None
            assert found.id == resolved.session_id
            assert found.channel_type == "webex"

    @pytest.mark.asyncio
    async def test_find_nonexistent_session(self, db_factory):
        """Test finding a session that doesn't exist."""
        resolver = SessionResolver()

        async with db_factory() as db:
            found = await resolver.find_session_by_channel(
                db=db,
                channel_type="telegram",
                external_thread_id="nonexistent",
            )

            assert found is None


class TestDatabaseModels:
    """Tests for database model changes."""

    @pytest.mark.asyncio
    async def test_session_channel_fields(self, db_factory):
        """Test that Session model has channel fields."""
        async with db_factory() as db:
            session = DBSession(
                id="test-session-1",
                agent_id="mo",
                title="Test Session",
                channel_type="telegram",
                external_thread_id="chat123",
                channel_user_id="user456",
                channel_user_name="Test User",
            )
            db.add(session)
            await db.commit()

            result = await db.execute(
                select(DBSession).where(DBSession.id == "test-session-1")
            )
            saved = result.scalar_one()

            assert saved.channel_type == "telegram"
            assert saved.external_thread_id == "chat123"
            assert saved.channel_user_id == "user456"
            assert saved.channel_user_name == "Test User"

    @pytest.mark.asyncio
    async def test_message_source_fields(self, db_factory):
        """Test that Message model has source fields."""
        async with db_factory() as db:
            # Create session first
            session = DBSession(
                id="test-session-2",
                agent_id="mo",
                title="Test",
            )
            db.add(session)

            message = DBMessage(
                id="test-msg-1",
                session_id="test-session-2",
                role="user",
                content="Hello",
                source_channel="imessage",
                external_message_id="ext-msg-123",
                sender_id="sender-456",
                sender_name="John Doe",
                attachments=[{"type": "image"}],
                redacted=False,
            )
            db.add(message)
            await db.commit()

            result = await db.execute(
                select(DBMessage).where(DBMessage.id == "test-msg-1")
            )
            saved = result.scalar_one()

            assert saved.source_channel == "imessage"
            assert saved.external_message_id == "ext-msg-123"
            assert saved.sender_id == "sender-456"
            assert saved.sender_name == "John Doe"
            assert saved.attachments == [{"type": "image"}]
            assert saved.redacted is False

    @pytest.mark.asyncio
    async def test_session_defaults_to_web(self, db_factory):
        """Test that Session defaults to web channel."""
        async with db_factory() as db:
            session = DBSession(
                id="test-session-3",
                agent_id="mo",
                title="Web Session",
            )
            db.add(session)
            await db.commit()

            result = await db.execute(
                select(DBSession).where(DBSession.id == "test-session-3")
            )
            saved = result.scalar_one()

            assert saved.channel_type == "web"

    @pytest.mark.asyncio
    async def test_message_defaults_to_web(self, db_factory):
        """Test that Message defaults to web source channel."""
        async with db_factory() as db:
            session = DBSession(
                id="test-session-4",
                agent_id="mo",
                title="Test",
            )
            db.add(session)

            message = DBMessage(
                id="test-msg-2",
                session_id="test-session-4",
                role="user",
                content="Hello from web",
            )
            db.add(message)
            await db.commit()

            result = await db.execute(
                select(DBMessage).where(DBMessage.id == "test-msg-2")
            )
            saved = result.scalar_one()

            assert saved.source_channel == "web"
