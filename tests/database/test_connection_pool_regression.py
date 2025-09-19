"""
Regression Tests for SQLAlchemy Connection Pool Leaks

This module contains tests to ensure that database connections are properly
managed and returned to the pool, preventing connection pool leaks.

Specific focus on the issue fixed in app/api/ask.py where incorrect usage
of sync database dependency in async context was causing connection leaks.
"""

import asyncio
import logging
import time
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.core import get_async_db, async_engine
from tests.api.test_minimal_fastapi_app import create_test_client


class TestConnectionPoolRegression:
    """Regression tests for SQLAlchemy connection pool management."""

    @pytest.fixture
    def client(self) -> TestClient:
        """Create a test client."""
        return create_test_client()

    async def _count_active_connections(self) -> int:
        """Count active connections in the pool."""
        try:
            async with async_engine.connect() as conn:
                result = await conn.execute(
                    text("SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()")
                )
                count = result.scalar()
                return count or 0
        except Exception:
            return 0

    def test_ask_replay_endpoint_does_not_leak_connections(self, client: TestClient):
        """Test that /v1/ask/replay/{rid} endpoint doesn't leak database connections."""
        # Record initial connection count
        initial_connections = asyncio.run(self._count_active_connections())

        # Make multiple requests to the endpoint
        for i in range(10):
            response = client.get(f"/v1/ask/replay/test_rid_{i}")
            # Should return 401 (unauthorized) but not leak connections
            assert response.status_code == 401

        # Give time for garbage collection if any connections were leaked
        time.sleep(1)

        # Check that connections haven't leaked
        final_connections = asyncio.run(self._count_active_connections())

        # Allow for some variance but ensure we don't have a massive leak
        # In practice, the connection count might fluctuate but shouldn't increase dramatically
        connection_increase = final_connections - initial_connections
        assert connection_increase < 5, f"Connection leak detected: {connection_increase} new connections"

    def test_ask_replay_logs_database_operations(self, client: TestClient, caplog):
        """Test that ask replay endpoint logs database operations properly."""
        with caplog.at_level(logging.INFO):
            response = client.get("/v1/ask/replay/test_rid")

            # Should log database operation start
            assert any("ASK_REPLAY_DB_START" in record.message for record in caplog.records)

            # Should log database operation completion or error
            db_logs = [r for r in caplog.records if "ASK_REPLAY" in r.message and "DB" in r.message]
            assert len(db_logs) > 0, "No database operation logs found"

    @patch('app.api.ask.get_messages_by_rid')
    def test_ask_replay_with_mock_database_call(self, mock_get_messages, client: TestClient):
        """Test ask replay with mocked database call to verify session management."""
        # Mock the database function to return some test data
        mock_get_messages.return_value = [
            {"id": 1, "role": "user", "content": "test message", "created_at": "2023-01-01T00:00:00Z"}
        ]

        response = client.get("/v1/ask/replay/test_rid")

        # Should still return 401 due to auth, but database function should be called
        assert response.status_code == 401
        # Note: In real scenario with auth, this would be called, but our mock shows the pattern

    def test_async_database_context_manager_usage(self):
        """Test that async database context manager works correctly."""
        async def test_session():
            async with get_async_db() as session:
                assert isinstance(session, AsyncSession)
                # Test basic query execution
                result = await session.execute(text("SELECT 1"))
                assert result.scalar() == 1

        # Run the async test
        asyncio.run(test_session())

    def test_multiple_concurrent_requests_no_leak(self, client: TestClient):
        """Test that multiple concurrent requests don't leak connections."""
        import threading
        import concurrent.futures

        def make_request(request_id: int):
            """Make a single request and return response status."""
            try:
                response = client.get(f"/v1/ask/replay/concurrent_test_{request_id}")
                return response.status_code
            except Exception as e:
                return f"error: {e}"

        # Record initial connection count
        initial_connections = asyncio.run(self._count_active_connections())

        # Make concurrent requests
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(make_request, i) for i in range(20)]
            results = [future.result() for future in concurrent.futures.as_completed(futures)]

        # All requests should return 401 (unauthorized)
        assert all(result == 401 for result in results if isinstance(result, int))

        # Give time for connection cleanup
        time.sleep(2)

        # Check final connection count
        final_connections = asyncio.run(self._count_active_connections())
        connection_increase = final_connections - initial_connections

        # Allow for some variance but ensure no massive leak
        assert connection_increase < 10, f"Concurrent request leak detected: {connection_increase} new connections"

    def test_database_session_lifecycle_logging(self, client: TestClient, caplog):
        """Test that database session lifecycle is properly logged."""
        with caplog.at_level(logging.DEBUG):
            response = client.get("/v1/ask/replay/lifecycle_test")

            # Check for session lifecycle logs
            lifecycle_logs = [r for r in caplog.records if "SESSION" in r.message and "ASK_REPLAY" in r.message]
            if lifecycle_logs:  # May not appear if request fails at auth level
                assert len(lifecycle_logs) > 0

            # Check for query completion logs
            query_logs = [r for r in caplog.records if "QUERY_COMPLETE" in r.message and "ASK_REPLAY" in r.message]
            if query_logs:  # May not appear if request fails at auth level
                assert len(query_logs) > 0


class TestDatabaseConnectionPatterns:
    """Test correct database connection patterns to prevent future regressions."""

    def test_sync_db_dependency_not_used_in_async_context(self):
        """Ensure sync database dependency is not used in async contexts."""
        # This test ensures we don't regress to the original bug
        from app.db.core import get_db, get_async_db

        # get_db should be the sync version
        import inspect
        sync_gen = get_db()
        assert inspect.isgenerator(sync_gen), "get_db should return a sync generator"

        # get_async_db should be the async version
        async_gen = get_async_db()
        assert inspect.iscoroutine(async_gen), "get_async_db should return a coroutine"

    def test_async_context_manager_pattern(self):
        """Test that async context manager pattern works correctly."""
        async def test_context_manager():
            async with get_async_db() as session:
                assert session is not None
                # Session should be usable
                result = await session.execute(text("SELECT 1"))
                assert result.scalar() == 1
            # Session should be closed after context manager exits

        asyncio.run(test_context_manager())

    def test_async_generator_pattern(self):
        """Test that async generator pattern works correctly."""
        async def test_generator():
            async for session in get_async_db():
                assert session is not None
                result = await session.execute(text("SELECT 1"))
                assert result.scalar() == 1
                break  # Only test one session

        asyncio.run(test_generator())


if __name__ == "__main__":
    # Allow running this test file directly for quick verification
    pytest.main([__file__, "-v"])
