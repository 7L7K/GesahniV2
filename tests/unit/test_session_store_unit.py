from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from app.session_store import (
    SessionCookieStore,
    SessionStatus,
    append_error,
    create_session,
    get_session,
    get_session_store,
    list_sessions,
    update_session,
    update_status,
)


class TestSessionCookieStore:
    """Test SessionCookieStore with both in-memory and Redis backends."""

    def test_init_memory_backend(self):
        """Test initialization with in-memory backend (no Redis)."""
        with patch.dict(os.environ, {}, clear=True):
            store = SessionCookieStore()
            assert store._redis_client is None
            assert store._memory_store == {}

    def test_init_redis_backend_available(self):
        """Test initialization with Redis backend available."""
        mock_redis = Mock()
        mock_redis.ping.return_value = True

        with patch.dict(os.environ, {"REDIS_URL": "redis://localhost:6379"}):
            with patch("redis.Redis") as mock_redis_class:
                mock_redis_class.from_url.return_value = mock_redis
                store = SessionCookieStore()
                assert store._redis_client is not None
                mock_redis.ping.assert_called_once()

    def test_init_redis_backend_unavailable(self):
        """Test fallback to in-memory when Redis is configured but unavailable."""
        with patch.dict(os.environ, {"REDIS_URL": "redis://localhost:6379"}):
            with patch("redis.Redis") as mock_redis_class:
                mock_redis_class.from_url.side_effect = Exception("Connection failed")
                store = SessionCookieStore()
                assert store._redis_client is None
                assert store._memory_store == {}

    def test_create_session_memory_backend(self):
        """Test creating session with in-memory backend."""
        with patch.dict(os.environ, {}, clear=True):
            store = SessionCookieStore()
            jti = "test-jti-123"
            expires_at = time.time() + 3600

            session_id = store.create_session(jti, expires_at)

            assert session_id.startswith("sess_")
            assert session_id in store._memory_store
            stored_jti, stored_expires = store._memory_store[session_id]
            assert stored_jti == jti
            assert stored_expires == expires_at

    def test_create_session_redis_backend(self):
        """Test creating session with Redis backend."""
        mock_redis = Mock()
        with patch.dict(os.environ, {"REDIS_URL": "redis://localhost:6379"}):
            with patch("redis.Redis") as mock_redis_class:
                mock_redis_class.from_url.return_value = mock_redis
                store = SessionCookieStore()

                jti = "test-jti-123"
                expires_at = time.time() + 3600

                session_id = store.create_session(jti, expires_at)

                assert session_id.startswith("sess_")
                expected_data = json.dumps({"jti": jti, "expires_at": expires_at})
                mock_redis.setex.assert_called_once()
                call_args = mock_redis.setex.call_args
                assert call_args[0][0].startswith("session:sess_")
                assert abs(call_args[0][1] - 3600) <= 1  # TTL (allow small variance due to timing)
                assert call_args[0][2] == expected_data

    def test_get_session_valid_memory_backend(self):
        """Test getting valid session from memory backend."""
        with patch.dict(os.environ, {}, clear=True):
            store = SessionCookieStore()
            jti = "test-jti-123"
            expires_at = time.time() + 3600

            session_id = store.create_session(jti, expires_at)
            retrieved_jti = store.get_session(session_id)

            assert retrieved_jti == jti

    def test_get_session_valid_redis_backend(self):
        """Test getting valid session from Redis backend."""
        mock_redis = Mock()
        jti = "test-jti-123"
        expires_at = time.time() + 3600
        session_data = json.dumps({"jti": jti, "expires_at": expires_at})

        mock_redis.get.return_value = session_data

        with patch.dict(os.environ, {"REDIS_URL": "redis://localhost:6379"}):
            with patch("redis.Redis") as mock_redis_class:
                mock_redis_class.from_url.return_value = mock_redis
                store = SessionCookieStore()

                retrieved_jti = store.get_session("sess_123")

                assert retrieved_jti == jti
                mock_redis.get.assert_called_once_with("session:sess_123")

    def test_get_session_expired_memory_backend(self):
        """Test getting expired session from memory backend."""
        with patch.dict(os.environ, {}, clear=True):
            store = SessionCookieStore()
            jti = "test-jti-123"
            expires_at = time.time() - 3600  # Already expired

            session_id = store.create_session(jti, expires_at)
            retrieved_jti = store.get_session(session_id)

            assert retrieved_jti is None
            assert session_id not in store._memory_store  # Should be cleaned up

    def test_get_session_expired_redis_backend(self):
        """Test getting expired session from Redis backend."""
        mock_redis = Mock()
        jti = "test-jti-123"
        expires_at = time.time() - 3600  # Already expired
        session_data = json.dumps({"jti": jti, "expires_at": expires_at})

        mock_redis.get.return_value = session_data

        with patch.dict(os.environ, {"REDIS_URL": "redis://localhost:6379"}):
            with patch("redis.Redis") as mock_redis_class:
                mock_redis_class.from_url.return_value = mock_redis
                store = SessionCookieStore()

                retrieved_jti = store.get_session("sess_123")

                assert retrieved_jti is None
                mock_redis.delete.assert_called_once_with("session:sess_123")

    def test_get_session_nonexistent(self):
        """Test getting nonexistent session."""
        with patch.dict(os.environ, {}, clear=True):
            store = SessionCookieStore()
            retrieved_jti = store.get_session("nonexistent")
            assert retrieved_jti is None

    def test_delete_session_memory_backend(self):
        """Test deleting session from memory backend."""
        with patch.dict(os.environ, {}, clear=True):
            store = SessionCookieStore()
            jti = "test-jti-123"
            expires_at = time.time() + 3600

            session_id = store.create_session(jti, expires_at)
            result = store.delete_session(session_id)

            assert result is True
            assert session_id not in store._memory_store

    def test_delete_session_redis_backend(self):
        """Test deleting session from Redis backend."""
        mock_redis = Mock()
        mock_redis.delete.return_value = 1

        with patch.dict(os.environ, {"REDIS_URL": "redis://localhost:6379"}):
            with patch("redis.Redis") as mock_redis_class:
                mock_redis_class.from_url.return_value = mock_redis
                store = SessionCookieStore()

                result = store.delete_session("sess_123")

                assert result is True
                mock_redis.delete.assert_called_once_with("session:sess_123")

    def test_delete_session_nonexistent(self):
        """Test deleting nonexistent session."""
        with patch.dict(os.environ, {}, clear=True):
            store = SessionCookieStore()
            result = store.delete_session("nonexistent")
            assert result is False

    def test_cleanup_expired_memory_backend(self):
        """Test cleanup of expired sessions in memory backend."""
        with patch.dict(os.environ, {}, clear=True):
            store = SessionCookieStore()

            # Create valid and expired sessions
            valid_jti = "valid-jti"
            valid_expires = time.time() + 3600
            expired_jti = "expired-jti"
            expired_expires = time.time() - 3600

            valid_session_id = store.create_session(valid_jti, valid_expires)
            expired_session_id = store.create_session(expired_jti, expired_expires)

            # Manually add expired session to simulate it wasn't cleaned up yet
            store._memory_store[expired_session_id] = (expired_jti, expired_expires)

            store.cleanup_expired()

            assert valid_session_id in store._memory_store
            assert expired_session_id not in store._memory_store

    def test_cleanup_expired_redis_backend(self):
        """Test cleanup of expired sessions in Redis backend (no-op)."""
        mock_redis = Mock()
        with patch.dict(os.environ, {"REDIS_URL": "redis://localhost:6379"}):
            with patch("redis.Redis") as mock_redis_class:
                mock_redis_class.from_url.return_value = mock_redis
                store = SessionCookieStore()

                store.cleanup_expired()  # Should be no-op for Redis

                # Verify no Redis calls were made
                mock_redis.assert_not_called()

    def test_cleanup_expired_standalone_function(self):
        """Test that cleanup_expired function exists and can be called."""
        from app.session_store import get_session_store
        store = get_session_store()
        # Just test that the method exists and can be called without error
        store.cleanup_expired()

    def test_concurrent_upserts_memory_backend(self):
        """Test concurrent session creation/updates in memory backend."""
        with patch.dict(os.environ, {}, clear=True):
            store = SessionCookieStore()

            def create_sessions(count=10):
                for i in range(count):
                    jti = f"jti-{i}"
                    expires_at = time.time() + 3600
                    store.create_session(jti, expires_at)

            # Run concurrent session creation
            threads = []
            for _ in range(5):
                thread = threading.Thread(target=create_sessions, args=(10,))
                threads.append(thread)
                thread.start()

            for thread in threads:
                thread.join()

            # Verify all sessions were created (should have 50 total)
            assert len(store._memory_store) == 50

    def test_concurrent_upserts_redis_backend(self):
        """Test concurrent session creation/updates in Redis backend."""
        mock_redis = Mock()
        with patch.dict(os.environ, {"REDIS_URL": "redis://localhost:6379"}):
            with patch("redis.Redis") as mock_redis_class:
                mock_redis_class.from_url.return_value = mock_redis
                store = SessionCookieStore()

                def create_sessions(count=10):
                    for i in range(count):
                        jti = f"jti-{i}"
                        expires_at = time.time() + 3600
                        store.create_session(jti, expires_at)

                # Run concurrent session creation
                threads = []
                for _ in range(5):
                    thread = threading.Thread(target=create_sessions, args=(10,))
                    threads.append(thread)
                    thread.start()

                for thread in threads:
                    thread.join()

                # Verify setex was called 50 times
                assert mock_redis.setex.call_count == 50

    def test_corrupt_token_handling_redis_backend(self):
        """Test handling of corrupt tokens in Redis backend."""
        mock_redis = Mock()
        # Return corrupt JSON
        mock_redis.get.return_value = "corrupt-json-data"

        with patch.dict(os.environ, {"REDIS_URL": "redis://localhost:6379"}):
            with patch("redis.Redis") as mock_redis_class:
                mock_redis_class.from_url.return_value = mock_redis
                store = SessionCookieStore()

                retrieved_jti = store.get_session("sess_123")

                assert retrieved_jti is None
                mock_redis.get.assert_called_once_with("session:sess_123")

    def test_corrupt_token_handling_redis_exception(self):
        """Test handling of Redis exceptions during token retrieval."""
        mock_redis = Mock()
        mock_redis.get.side_effect = Exception("Redis connection error")

        with patch.dict(os.environ, {"REDIS_URL": "redis://localhost:6379"}):
            with patch("redis.Redis") as mock_redis_class:
                mock_redis_class.from_url.return_value = mock_redis
                store = SessionCookieStore()

                retrieved_jti = store.get_session("sess_123")

                assert retrieved_jti is None
                mock_redis.get.assert_called_once_with("session:sess_123")

    def test_corrupt_token_handling_redis_delete_exception(self):
        """Test handling of Redis exceptions during token deletion."""
        mock_redis = Mock()
        mock_redis.delete.side_effect = Exception("Redis connection error")

        with patch.dict(os.environ, {"REDIS_URL": "redis://localhost:6379"}):
            with patch("redis.Redis") as mock_redis_class:
                mock_redis_class.from_url.return_value = mock_redis
                store = SessionCookieStore()

                result = store.delete_session("sess_123")

                assert result is False
                mock_redis.delete.assert_called_once_with("session:sess_123")


class TestSessionMetadataStore:
    """Test session metadata file operations."""

    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("app.session_store.SESSIONS_DIR", Path(tmpdir)):
                yield tmpdir

    def test_create_session_metadata(self, temp_dir):
        """Test creating new session metadata."""
        meta = create_session()

        assert "session_id" in meta
        assert "created_at" in meta
        assert meta["status"] == SessionStatus.PENDING.value
        assert meta["retry_count"] == 0
        assert meta["errors"] == []

        # Verify file was created
        session_path = os.path.join(temp_dir, meta["session_id"], "meta.json")
        assert os.path.exists(session_path)

    def test_update_session(self, temp_dir):
        """Test updating session metadata."""
        meta = create_session()
        session_id = meta["session_id"]

        updated_meta = update_session(session_id, status=SessionStatus.PROCESSING_WHISPER.value, retry_count=1)

        assert updated_meta["status"] == SessionStatus.PROCESSING_WHISPER.value
        assert updated_meta["retry_count"] == 1

    def test_update_status(self, temp_dir):
        """Test updating session status."""
        meta = create_session()
        session_id = meta["session_id"]

        updated_meta = update_status(session_id, SessionStatus.TRANSCRIBED)

        assert updated_meta["status"] == SessionStatus.TRANSCRIBED.value

    def test_append_error(self, temp_dir):
        """Test appending error to session."""
        meta = create_session()
        session_id = meta["session_id"]

        updated_meta = append_error(session_id, "Test error 1")
        updated_meta = append_error(session_id, "Test error 2")

        assert len(updated_meta["errors"]) == 2
        assert "Test error 1" in updated_meta["errors"]
        assert "Test error 2" in updated_meta["errors"]

    def test_get_session(self, temp_dir):
        """Test getting session metadata."""
        meta = create_session()
        session_id = meta["session_id"]

        retrieved_meta = get_session(session_id)

        assert retrieved_meta == meta

    def test_get_session_nonexistent(self, temp_dir):
        """Test getting nonexistent session."""
        retrieved_meta = get_session("nonexistent")
        assert retrieved_meta == {}

    def test_list_sessions_all(self, temp_dir):
        """Test listing all sessions."""
        meta1 = create_session()
        meta2 = create_session()

        sessions = list_sessions()

        assert len(sessions) == 2
        session_ids = {s["session_id"] for s in sessions}
        assert meta1["session_id"] in session_ids
        assert meta2["session_id"] in session_ids

    def test_list_sessions_by_status(self, temp_dir):
        """Test listing sessions by status."""
        meta1 = create_session()
        meta2 = create_session()
        update_status(meta2["session_id"], SessionStatus.PROCESSING_WHISPER)

        pending_sessions = list_sessions(SessionStatus.PENDING)
        processing_sessions = list_sessions(SessionStatus.PROCESSING_WHISPER)

        assert len(pending_sessions) == 1
        assert pending_sessions[0]["session_id"] == meta1["session_id"]
        assert len(processing_sessions) == 1
        assert processing_sessions[0]["session_id"] == meta2["session_id"]

    def test_list_sessions_sorted_by_creation(self, temp_dir):
        """Test that sessions are sorted by creation time (newest first)."""
        meta1 = create_session()
        time.sleep(1.1)  # Sleep for 1.1 seconds to ensure different timestamps
        meta2 = create_session()

        sessions = list_sessions()

        assert len(sessions) == 2
        # Should be sorted with newest first (compare timestamps directly)
        time1 = meta1["created_at"]
        time2 = meta2["created_at"]
        assert time2 > time1  # meta2 was created after meta1

        # Check that the first session has the newer timestamp
        assert sessions[0]["created_at"] >= sessions[1]["created_at"]

    def test_concurrent_session_operations(self, temp_dir):
        """Test concurrent session metadata operations."""
        def create_and_update_sessions(count=5):
            for i in range(count):
                meta = create_session()
                session_id = meta["session_id"]
                update_session(session_id, custom_field=f"value-{i}")
                append_error(session_id, f"error-{i}")

        # Run concurrent operations
        threads = []
        for _ in range(3):
            thread = threading.Thread(target=create_and_update_sessions, args=(5,))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # Verify all sessions were created (should have 15 total)
        sessions = list_sessions()
        assert len(sessions) == 15

        # Verify all sessions have custom fields and errors
        for session in sessions:
            assert "custom_field" in session
            assert len(session["errors"]) == 1


class TestGlobalSessionStore:
    """Test global session store instance."""

    def test_get_session_store_returns_instance(self):
        """Test that get_session_store returns a SessionCookieStore instance."""
        store = get_session_store()
        assert isinstance(store, SessionCookieStore)

    def test_get_session_store_returns_same_instance(self):
        """Test that get_session_store returns the same instance on multiple calls."""
        store1 = get_session_store()
        store2 = get_session_store()
        assert store1 is store2
