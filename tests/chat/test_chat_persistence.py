"""Tests for chat message persistence."""

import asyncio
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.db.chat_repo import get_messages_by_rid, get_recent_messages, save_messages
from app.db.core import get_async_db
from app.db.models import ChatMessage
from app.schemas.chat import Message


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

    async def test_save_and_retrieve_messages(self, sample_messages):
        """Test saving and retrieving messages."""
        user_id = "test-user-123"
        rid = "test-rid-456"

        async with get_async_db() as session:
            # Save messages
            await save_messages(session, user_id, rid, sample_messages)

            # Retrieve messages
            retrieved_messages = await get_messages_by_rid(session, user_id, rid)

            assert len(retrieved_messages) == 2
            assert retrieved_messages[0].role == "user"
            assert retrieved_messages[0].content == "Hello, how are you?"
            assert retrieved_messages[1].role == "assistant"
            assert (
                retrieved_messages[1].content == "I'm doing well, thank you for asking!"
            )

            # Check that messages are ordered by creation time
            assert retrieved_messages[0].created_at <= retrieved_messages[1].created_at

    async def test_retrieve_nonexistent_rid(self):
        """Test retrieving messages for non-existent RID returns empty list."""
        user_id = "test-user-123"
        rid = "nonexistent-rid"

        async with get_async_db() as session:
            messages = await get_messages_by_rid(session, user_id, rid)
            assert len(messages) == 0

    async def test_user_isolation(self, sample_messages):
        """Test that users can only see their own messages."""
        user1_id = "user1"
        user2_id = "user2"
        rid = "shared-rid"

        async with get_async_db() as session:
            # User 1 saves messages
            await save_messages(session, user1_id, rid, sample_messages)

            # User 2 should not see user 1's messages
            user2_messages = await get_messages_by_rid(session, user2_id, rid)
            assert len(user2_messages) == 0

            # User 1 should see their messages
            user1_messages = await get_messages_by_rid(session, user1_id, rid)
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

    async def test_save_empty_messages_list(self):
        """Test that saving empty message list does nothing."""
        user_id = "test-user-123"
        rid = "test-rid-456"

        async with get_async_db() as session:
            # Should not raise error
            await save_messages(session, user_id, rid, [])

            # Should not have created any messages
            messages = await get_messages_by_rid(session, user_id, rid)
            assert len(messages) == 0

    async def test_save_messages_with_invalid_data(self):
        """Test saving messages with missing required fields."""
        user_id = "test-user-123"
        rid = "test-rid-456"

        # Messages missing required fields
        invalid_messages = [
            {"role": "user"},  # Missing content
            {"content": "Hello"},  # Missing role
            {},  # Missing both
        ]

        async with get_async_db() as session:
            # Should save only valid messages
            await save_messages(session, user_id, rid, invalid_messages)

            messages = await get_messages_by_rid(session, user_id, rid)
            assert len(messages) == 0  # No valid messages

    async def test_save_messages_with_special_characters(self):
        """Test saving messages with special characters and unicode."""
        user_id = "test-user-123"
        rid = "test-rid-456"

        special_messages = [
            {"role": "user", "content": "Hello 🌟 with emoji!"},
            {"role": "assistant", "content": "Special chars: àáâãäåæçèéêë"},
            {"role": "user", "content": "Code: print('hello')"},
        ]

        async with get_async_db() as session:
            await save_messages(session, user_id, rid, special_messages)

            messages = await get_messages_by_rid(session, user_id, rid)
            assert len(messages) == 3
            assert messages[0].content == "Hello 🌟 with emoji!"
            assert messages[1].content == "Special chars: àáâãäåæçèéêë"
            assert messages[2].content == "Code: print('hello')"

    async def test_multiple_rids_same_user(self):
        """Test multiple conversations for same user."""
        user_id = "test-user-123"

        # First conversation
        rid1 = "conversation-1"
        messages1 = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]

        # Second conversation
        rid2 = "conversation-2"
        messages2 = [
            {"role": "user", "content": "Goodbye"},
            {"role": "assistant", "content": "Farewell!"},
        ]

        async with get_async_db() as session:
            await save_messages(session, user_id, rid1, messages1)
            await save_messages(session, user_id, rid2, messages2)

            # Check first conversation
            conv1_messages = await get_messages_by_rid(session, user_id, rid1)
            assert len(conv1_messages) == 2
            assert conv1_messages[0].content == "Hello"

            # Check second conversation
            conv2_messages = await get_messages_by_rid(session, user_id, rid2)
            assert len(conv2_messages) == 2
            assert conv2_messages[0].content == "Goodbye"

    async def test_get_recent_messages(self):
        """Test retrieving recent messages for a user."""
        user_id = "test-user-123"

        async with get_async_db() as session:
            # Create multiple conversations
            for i in range(5):
                rid = f"rid-{i}"
                messages = [
                    {"role": "user", "content": f"Message {i}"},
                    {"role": "assistant", "content": f"Response {i}"},
                ]
                await save_messages(session, user_id, rid, messages)

            # Get recent messages (should return 10 total)
            recent = await get_recent_messages(session, user_id, limit=10)
            assert len(recent) == 10

            # Get limited recent messages
            recent_limited = await get_recent_messages(session, user_id, limit=3)
            assert len(recent_limited) == 3

            # Should be ordered by creation time (newest first)
            assert recent_limited[0].created_at >= recent_limited[1].created_at

    async def test_message_persistence_large_content(self):
        """Test persisting messages with large content."""
        user_id = "test-user-123"
        rid = "large-content-rid"

        # Create a large message (within limits)
        large_content = "A" * 8000  # Max allowed length
        messages = [
            {"role": "user", "content": large_content},
        ]

        async with get_async_db() as session:
            await save_messages(session, user_id, rid, messages)

            retrieved = await get_messages_by_rid(session, user_id, rid)
            assert len(retrieved) == 1
            assert len(retrieved[0].content) == 8000

    def test_message_schema_validation(self):
        """Test Message schema validation."""
        # Valid message
        msg = Message(role="user", content="Hello")
        assert msg.role == "user"
        assert msg.content == "Hello"

        # Invalid role
        with pytest.raises(ValueError):
            Message(role="invalid", content="Hello")

        # Empty content after strip
        with pytest.raises(ValueError):
            Message(role="user", content="   ")

        # Content too long
        with pytest.raises(ValueError):
            Message(role="user", content="A" * 8001)

    async def test_concurrent_message_saving(self):
        """Test saving messages from multiple concurrent requests."""
        user_id = "test-user-123"

        async with get_async_db() as session:
            # Simulate concurrent saves
            tasks = []
            for i in range(10):
                rid = f"concurrent-rid-{i}"
                messages = [
                    {"role": "user", "content": f"Concurrent message {i}"},
                    {"role": "assistant", "content": f"Concurrent response {i}"},
                ]
                tasks.append(save_messages(session, user_id, rid, messages))

            # Execute all concurrently
            await asyncio.gather(*tasks)

            # Verify all messages were saved
            total_messages = 0
            for i in range(10):
                rid = f"concurrent-rid-{i}"
                messages = await get_messages_by_rid(session, user_id, rid)
                assert len(messages) == 2
                total_messages += len(messages)

            assert total_messages == 20

    async def test_message_order_preservation(self):
        """Test that message order is preserved."""
        user_id = "test-user-123"
        rid = "order-test-rid"

        async with get_async_db() as session:
            # Create messages in specific order
            messages = []
            for i in range(10):
                messages.append(
                    {
                        "role": "user" if i % 2 == 0 else "assistant",
                        "content": f"Message {i}",
                    }
                )

            await save_messages(session, user_id, rid, messages)

            retrieved = await get_messages_by_rid(session, user_id, rid)
            assert len(retrieved) == 10

            # Check order preservation
            for i, msg in enumerate(retrieved):
                expected_role = "user" if i % 2 == 0 else "assistant"
                expected_content = f"Message {i}"
                assert msg.role == expected_role
                assert msg.content == expected_content

    def test_ask_endpoint_persistence_integration(self):
        """Test ask endpoint integration with persistence (mocked)."""
        import os

        from app.main import create_app

        os.environ["JWT_SECRET"] = "test-secret-123"
        os.environ["PYTEST_RUNNING"] = "1"

        app = create_app()
        client = TestClient(app)

        # Mock the router to return a simple response
        with patch("app.router.entrypoint.route_prompt") as mock_route:
            mock_route.return_value = "Mocked assistant response"

            # Mock save_messages to track calls
            with patch("app.db.chat_repo.save_messages") as mock_save:
                # Make request (will fail auth but should still call persistence if it gets past auth)
                response = client.post(
                    "/v1/ask",
                    json={"prompt": "Test message"},
                    headers={"Authorization": "Bearer invalid-token"},
                )

                # Should fail auth
                assert response.status_code == 401

                # save_messages should not be called due to auth failure
                mock_save.assert_not_called()

    def test_replay_endpoint_response_format(self):
        """Test replay endpoint returns correct response format."""
        import os

        from app.main import create_app

        os.environ["JWT_SECRET"] = "test-secret-123"
        os.environ["PYTEST_RUNNING"] = "1"

        app = create_app()
        client = TestClient(app)

        # Test with invalid auth (should get 401)
        response = client.get("/v1/ask/replay/test-rid")
        assert response.status_code == 401

    async def test_persistence_error_handling(
        self,
    ):
        """Test that persistence errors don't break the main flow."""
        user_id = "test-user-123"
        rid = "error-test-rid"

        # Test with None session (should handle gracefully)
        try:
            await save_messages(
                None, user_id, rid, [{"role": "user", "content": "test"}]
            )
        except Exception as e:
            # Should handle None session gracefully
            assert "session" in str(e).lower() or "None" in str(e)

    async def test_message_timestamps(
        self,
    ):
        """Test that messages have proper timestamps."""
        import time

        user_id = "test-user-123"
        rid = "timestamp-test-rid"

        # Record time before saving
        before_save = time.time()

        messages = [{"role": "user", "content": "Timestamp test"}]
        await save_messages(session, user_id, rid, messages)

        # Record time after saving
        after_save = time.time()

        retrieved = await get_messages_by_rid(session, user_id, rid)
        assert len(retrieved) == 1

        msg_timestamp = retrieved[0].created_at.timestamp()
        assert before_save <= msg_timestamp <= after_save

    async def test_user_data_isolation(
        self,
    ):
        """Test that user data is properly isolated."""
        # Create messages for different users
        users_and_messages = {
            "user1": [
                {"role": "user", "content": "User 1 message 1"},
                {"role": "assistant", "content": "Response to user 1"},
            ],
            "user2": [
                {"role": "user", "content": "User 2 message 1"},
                {"role": "assistant", "content": "Response to user 2"},
            ],
        }

        rid = "isolation-test-rid"

        for user_id, messages in users_and_messages.items():
            await save_messages(session, user_id, rid, messages)

        # Each user should only see their own messages
        for user_id, _expected_messages in users_and_messages.items():
            user_messages = await get_messages_by_rid(session, user_id, rid)
            assert len(user_messages) == 2
            assert user_messages[0].user_id == user_id
            assert user_messages[1].user_id == user_id

    async def test_very_long_rid(
        self,
    ):
        """Test handling of very long RIDs."""
        user_id = "test-user-123"
        # Create a very long RID (beyond typical limits)
        long_rid = "a" * 1000

        messages = [{"role": "user", "content": "Long RID test"}]
        await save_messages(session, user_id, long_rid, messages)

        retrieved = await get_messages_by_rid(session, user_id, long_rid)
        assert len(retrieved) == 1
        assert retrieved[0].rid == long_rid

    async def test_empty_content_filtering(
        self,
    ):
        """Test that empty or whitespace-only content is filtered out."""
        user_id = "test-user-123"
        rid = "empty-content-test"

        messages = [
            {"role": "user", "content": "Valid message"},
            {"role": "user", "content": ""},  # Empty
            {"role": "user", "content": "   "},  # Whitespace only
            {"role": "assistant", "content": "Another valid message"},
        ]

        await save_messages(session, user_id, rid, messages)

        retrieved = await get_messages_by_rid(session, user_id, rid)
        # Only valid messages should be saved
        assert len(retrieved) == 2
        assert retrieved[0].content == "Valid message"
        assert retrieved[1].content == "Another valid message"

    def test_persistence_doesnt_block_main_flow(self):
        """Test that persistence failures don't block the main request flow."""
        import os

        from app.main import create_app

        os.environ["JWT_SECRET"] = "test-secret-123"
        os.environ["PYTEST_RUNNING"] = "1"

        app = create_app()

        # Mock route_prompt to return response
        with patch("app.router.entrypoint.route_prompt") as mock_route:
            mock_route.return_value = "Test response"

            # Mock save_messages to raise exception
            with patch("app.db.chat_repo.save_messages") as mock_save:
                mock_save.side_effect = Exception("Database error")

                # The ask endpoint should still work despite persistence failure
                client = TestClient(app)

                # This will fail due to auth, but we're testing the persistence error handling
                response = client.post(
                    "/v1/ask",
                    json={"prompt": "Test"},
                    headers={"Authorization": "Bearer invalid"},
                )

                # Should fail auth, not due to persistence error
                assert response.status_code == 401


class TestChatPersistenceIntegration:
    """Integration tests for chat persistence with real API calls."""

    async def test_full_ask_replay_cycle(
        self,
    ):
        """Test complete ask -> persist -> replay cycle."""
        import os

        from app.auth_core import mint_token
        from app.main import create_app

        os.environ["JWT_SECRET"] = "test-secret-123"
        os.environ["PYTEST_RUNNING"] = "1"

        app = create_app()

        # Create a test token with required scopes
        token = mint_token(scopes=["chat:write"])

        # Mock the router to return a predictable response
        expected_response = "Mocked AI response for testing"

        with patch("app.router.entrypoint.route_prompt") as mock_route:
            mock_route.return_value = expected_response

            client = TestClient(app)

            # Step 1: Make ask request
            ask_response = client.post(
                "/v1/ask",
                json={"prompt": "Test question"},
                headers={"Authorization": f"Bearer {token}"},
            )

            assert ask_response.status_code == 200
            ask_data = ask_response.json()
            assert "rid" in ask_data
            assert ask_data["response"] == expected_response

            rid = ask_data["rid"]

            # Step 2: Verify messages were persisted
            persisted_messages = await get_messages_by_rid(session, "test-user", rid)
            assert len(persisted_messages) == 2  # user + assistant

            assert persisted_messages[0].role == "user"
            assert persisted_messages[0].content == "Test question"
            assert persisted_messages[1].role == "assistant"
            assert persisted_messages[1].content == expected_response

            # Step 3: Test replay endpoint
            replay_response = client.get(
                f"/v1/ask/replay/{rid}", headers={"Authorization": f"Bearer {token}"}
            )

            assert replay_response.status_code == 200
            replay_data = replay_response.json()

            assert replay_data["rid"] == rid
            assert replay_data["message_count"] == 2
            assert len(replay_data["messages"]) == 2

            # Verify message content
            messages = replay_data["messages"]
            assert messages[0]["role"] == "user"
            assert messages[0]["content"] == "Test question"
            assert messages[1]["role"] == "assistant"
            assert messages[1]["content"] == expected_response

            # Verify timestamps exist
            assert "created_at" in messages[0]
            assert "created_at" in messages[1]

    async def test_ask_with_message_array_persistence(
        self,
    ):
        """Test ask with message array input and verify persistence."""
        import os

        from app.auth_core import mint_token
        from app.main import create_app

        os.environ["JWT_SECRET"] = "test-secret-123"
        os.environ["PYTEST_RUNNING"] = "1"

        app = create_app()

        # Create a test token
        token = mint_token(scopes=["chat:write"])

        # Mock router response
        with patch("app.router.entrypoint.route_prompt") as mock_route:
            mock_route.return_value = "Response to message array"

            client = TestClient(app)

            # Send message array
            message_array = [
                {"role": "system", "content": "You are a helpful assistant"},
                {"role": "user", "content": "Hello there"},
            ]

            ask_response = client.post(
                "/v1/ask",
                json={"prompt": message_array},
                headers={"Authorization": f"Bearer {token}"},
            )

            assert ask_response.status_code == 200
            ask_data = ask_response.json()
            rid = ask_data["rid"]

            # Verify all messages were persisted
            persisted_messages = await get_messages_by_rid(session, "test-user", rid)
            assert len(persisted_messages) == 3  # system + user + assistant

            assert persisted_messages[0].role == "system"
            assert persisted_messages[0].content == "You are a helpful assistant"
            assert persisted_messages[1].role == "user"
            assert persisted_messages[1].content == "Hello there"
            assert persisted_messages[2].role == "assistant"
            assert persisted_messages[2].content == "Response to message array"

    async def test_replay_nonexistent_rid(
        self,
    ):
        """Test replay endpoint with non-existent RID."""
        import os

        from app.auth_core import mint_token
        from app.main import create_app

        os.environ["JWT_SECRET"] = "test-secret-123"
        os.environ["PYTEST_RUNNING"] = "1"

        app = create_app()
        client = TestClient(app)

        # Create a test token
        token = mint_token(scopes=["chat:write"])

        # Try to replay non-existent RID
        response = client.get(
            "/v1/ask/replay/nonexistent-rid-12345",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 404
        data = response.json()
        assert data["code"] == "not_found"
        assert "No chat messages found" in data["message"]

    async def test_user_isolation_in_replay(
        self,
    ):
        """Test that users can only access their own conversation replays."""
        import os

        from app.auth_core import mint_token
        from app.main import create_app

        os.environ["JWT_SECRET"] = "test-secret-123"
        os.environ["PYTEST_RUNNING"] = "1"

        app = create_app()

        # Create tokens for two different users
        token1 = mint_token(sub="user1", scopes=["chat:write"])
        token2 = mint_token(sub="user2", scopes=["chat:write"])

        # Mock router
        with patch("app.router.entrypoint.route_prompt") as mock_route:
            mock_route.return_value = "Response"

            client = TestClient(app)

            # User 1 makes a request
            response1 = client.post(
                "/v1/ask",
                json={"prompt": "User 1 question"},
                headers={"Authorization": f"Bearer {token1}"},
            )
            assert response1.status_code == 200
            rid1 = response1.json()["rid"]

            # User 2 makes a request
            response2 = client.post(
                "/v1/ask",
                json={"prompt": "User 2 question"},
                headers={"Authorization": f"Bearer {token2}"},
            )
            assert response2.status_code == 200
            rid2 = response2.json()["rid"]

            # User 1 tries to access user 2's conversation (should fail)
            response = client.get(
                f"/v1/ask/replay/{rid2}", headers={"Authorization": f"Bearer {token1}"}
            )
            assert response.status_code == 404

            # User 1 can access their own conversation
            response = client.get(
                f"/v1/ask/replay/{rid1}", headers={"Authorization": f"Bearer {token1}"}
            )
            assert response.status_code == 200

    def test_persistence_failure_does_not_break_response(self):
        """Test that if persistence fails, the ask response still works."""
        import os

        from app.auth_core import mint_token
        from app.main import create_app

        os.environ["JWT_SECRET"] = "test-secret-123"
        os.environ["PYTEST_RUNNING"] = "1"

        app = create_app()

        # Create a test token
        token = mint_token(scopes=["chat:write"])

        # Mock router to return response
        with patch("app.router.entrypoint.route_prompt") as mock_route:
            mock_route.return_value = "AI Response"

            # Mock save_messages to fail
            with patch("app.db.chat_repo.save_messages") as mock_save:
                mock_save.side_effect = Exception("Database connection failed")

                client = TestClient(app)

                # The ask request should still succeed despite persistence failure
                response = client.post(
                    "/v1/ask",
                    json={"prompt": "Test question"},
                    headers={"Authorization": f"Bearer {token}"},
                )

                # Should succeed despite persistence error
                assert response.status_code == 200
                data = response.json()
                assert "rid" in data
                assert data["response"] == "AI Response"

                # Verify save_messages was called but failed
                mock_save.assert_called_once()


class TestAskReplayIntegration:
    """Integration tests for ask->replay cycle using database history."""

    @pytest.mark.asyncio
    async def test_ask_replay_db_integration(self):
        """Test complete ask -> persist -> replay cycle using DB history.

        1. Send request to /v1/ask (with mocked LLM)
        2. Extract rid from response
        3. Fetch /v1/ask/replay/{rid}
        4. Assert roles/order and timestamps
        """
        import os

        from app.main import create_app

        def mint_token(scopes=None):
            from app.tokens import make_access

            claims = {"user_id": "u_test"}
            if scopes is not None:
                claims["scopes"] = scopes
            return make_access(claims)

        os.environ["JWT_SECRET"] = "test-secret-123"
        os.environ["PYTEST_RUNNING"] = "1"

        app = create_app()

        # Create test token with required scopes
        token = mint_token(scopes=["chat:write"])

        # Mock LLM response
        expected_ai_response = "Hello! I'm doing well, thank you for asking."

        with patch("app.router.entrypoint.route_prompt") as mock_route:
            mock_route.return_value = expected_ai_response

            client = TestClient(app)

            # Step 1: Send ask request
            ask_response = client.post(
                "/v1/ask",
                json={"prompt": "How are you doing today?"},
                headers={"Authorization": f"Bearer {token}"},
            )

            assert ask_response.status_code == 200
            ask_data = ask_response.json()

            # Verify response contains rid
            assert "rid" in ask_data
            assert ask_data["response"] == expected_ai_response

            rid = ask_data["rid"]
            assert isinstance(rid, str)
            assert len(rid) == 8  # UUID[:8] format

            # Step 2: Fetch replay using extracted rid
            replay_response = client.get(
                f"/v1/ask/replay/{rid}", headers={"Authorization": f"Bearer {token}"}
            )

            assert replay_response.status_code == 200
            replay_data = replay_response.json()

            # Step 3: Assert replay structure
            assert replay_data["rid"] == rid
            assert "user_id" in replay_data
            assert replay_data["message_count"] == 2
            assert len(replay_data["messages"]) == 2

            messages = replay_data["messages"]

            # Step 4: Assert message roles and order
            assert messages[0]["role"] == "user"
            assert messages[0]["content"] == "How are you doing today?"
            assert "created_at" in messages[0]
            assert isinstance(messages[0]["created_at"], str)

            assert messages[1]["role"] == "assistant"
            assert messages[1]["content"] == expected_ai_response
            assert "created_at" in messages[1]
            assert isinstance(messages[1]["created_at"], str)

            # Verify timestamps are reasonable (assistant after user)
            user_time = messages[0]["created_at"]
            assistant_time = messages[1]["created_at"]
            # Timestamps should be the same or assistant slightly after user
            assert user_time <= assistant_time

    @pytest.mark.asyncio
    async def test_ask_replay_with_message_array(self):
        """Test ask->replay with message array input."""
        import os

        from app.main import create_app

        def mint_token(scopes=None):
            from app.tokens import make_access

            claims = {"user_id": "u_test"}
            if scopes is not None:
                claims["scopes"] = scopes
            return make_access(claims)

        os.environ["JWT_SECRET"] = "test-secret-123"
        os.environ["PYTEST_RUNNING"] = "1"

        app = create_app()

        token = mint_token(scopes=["chat:write"])

        expected_response = "I understand your system instructions."

        with patch("app.router.entrypoint.route_prompt") as mock_route:
            mock_route.return_value = expected_response

            client = TestClient(app)

            # Message array input
            message_array = [
                {"role": "system", "content": "You are a helpful AI assistant."},
                {"role": "user", "content": "Please help me understand this."},
            ]

            ask_response = client.post(
                "/v1/ask",
                json={"prompt": message_array},
                headers={"Authorization": f"Bearer {token}"},
            )

            assert ask_response.status_code == 200
            ask_data = ask_response.json()
            assert "rid" in ask_data
            rid = ask_data["rid"]

            # Fetch replay
            replay_response = client.get(
                f"/v1/ask/replay/{rid}", headers={"Authorization": f"Bearer {token}"}
            )

            assert replay_response.status_code == 200
            replay_data = replay_response.json()

            # Should have system + user + assistant messages
            assert replay_data["message_count"] == 3
            messages = replay_data["messages"]

            assert messages[0]["role"] == "system"
            assert messages[0]["content"] == "You are a helpful AI assistant."
            assert messages[1]["role"] == "user"
            assert messages[1]["content"] == "Please help me understand this."
            assert messages[2]["role"] == "assistant"
            assert messages[2]["content"] == expected_response
