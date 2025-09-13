"""Tests for chat message persistence."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.chat_repo import get_messages_by_rid, save_messages
from app.db.models import ChatMessage


class TestChatPersistence:
    """Test chat message persistence functionality."""

    @pytest.fixture
    def sample_messages(self):
        """Sample messages for testing."""
        return [
            {"role": "user", "content": "Hello, how are you?"},
            {"role": "assistant", "content": "I'm doing well, thank you for asking!"},
        ]

    def test_chat_message_model_creation(self, sample_messages):
        """Test that ChatMessage model can be created."""
        user_id = "test-user-123"
        rid = "test-rid-456"

        # Create ChatMessage instances
        messages = []
        for msg in sample_messages:
            chat_msg = ChatMessage(
                user_id=user_id, rid=rid, role=msg["role"], content=msg["content"]
            )
            messages.append(chat_msg)

        assert len(messages) == 2
        assert messages[0].role == "user"
        assert messages[0].content == "Hello, how are you?"
        assert messages[1].role == "assistant"
        assert messages[1].rid == rid
        assert messages[0].user_id == user_id

    async def test_save_and_retrieve_messages(
        self, sample_messages, async_session: AsyncSession
    ):
        """Test saving and retrieving messages."""
        user_id = "test-user-123"
        rid = "test-rid-456"

        # Save messages
        await save_messages(async_session, user_id, rid, sample_messages)

        # Retrieve messages
        retrieved_messages = await get_messages_by_rid(async_session, user_id, rid)

        assert len(retrieved_messages) == 2
        assert retrieved_messages[0].role == "user"
        assert retrieved_messages[0].content == "Hello, how are you?"
        assert retrieved_messages[1].role == "assistant"
        assert retrieved_messages[1].content == "I'm doing well, thank you for asking!"

        # Check that messages are ordered by creation time
        assert retrieved_messages[0].created_at <= retrieved_messages[1].created_at

    async def test_retrieve_nonexistent_rid(self, async_session: AsyncSession):
        """Test retrieving messages for non-existent RID returns empty list."""
        user_id = "test-user-123"
        rid = "nonexistent-rid"

        messages = await get_messages_by_rid(async_session, user_id, rid)
        assert len(messages) == 0

    async def test_user_isolation(self, sample_messages, async_session: AsyncSession):
        """Test that users can only see their own messages."""
        user1_id = "user1"
        user2_id = "user2"
        rid = "shared-rid"

        # User 1 saves messages
        await save_messages(async_session, user1_id, rid, sample_messages)

        # User 2 should not see user 1's messages
        user2_messages = await get_messages_by_rid(async_session, user2_id, rid)
        assert len(user2_messages) == 0

        # User 1 should see their messages
        user1_messages = await get_messages_by_rid(async_session, user1_id, rid)
        assert len(user1_messages) == 2

    def test_replay_endpoint_structure(self):
        """Test that replay endpoint has correct structure."""
        import os

        from app.main import create_app

        os.environ["JWT_SECRET"] = "test-secret-123"
        os.environ["PYTEST_RUNNING"] = "1"

        app = create_app()

        # Check that /v1/ask/replay/{rid} route exists
        routes = [route.path for route in app.routes if hasattr(route, "path")]
        assert "/v1/ask/replay/{rid}" in routes

        print("✅ Replay endpoint route exists in application")
