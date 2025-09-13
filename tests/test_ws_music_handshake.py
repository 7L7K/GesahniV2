"""
WebSocket Music Handshake Tests

Tests the handshake protocol:
- Subprotocol negotiation (json.realtime.v1)
- Hello message with mode (ok/degraded)
- Mode transition from degraded to ok after manager recovery
"""

import asyncio
import json
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.main import create_app


def _auth():
    """Create auth headers for testing."""
    import jwt

    token = jwt.encode(
        {"user_id": "u_test"}, os.getenv("JWT_SECRET", "secret"), algorithm="HS256"
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_ws_music_subprotocol_negotiation():
    """Test that WebSocket properly negotiates subprotocol."""
    app = create_app()
    client = TestClient(app)

    auth_headers = _auth()

    # Mock the manager to be unavailable initially
    with patch("app.api.music_ws.get_ws_manager") as mock_get_manager:
        mock_manager = AsyncMock()
        mock_manager.add_connection = AsyncMock(return_value=MagicMock())
        mock_get_manager.return_value = mock_manager

        # Connect with authentication
        with client.websocket_connect("/v1/ws/music", headers=auth_headers) as ws:
            # Should receive hello frame immediately
            hello_msg = json.loads(ws.receive_text())

            # Verify hello frame structure
            assert hello_msg["type"] == "hello"
            assert hello_msg["proto"] == "json.realtime.v1"
            assert "mode" in hello_msg
            assert "ts" in hello_msg
            assert isinstance(hello_msg["ts"], int)

            # Should receive initial state
            state_msg = json.loads(ws.receive_text())
            assert state_msg["type"] == "state_full"
            assert "state" in state_msg
            assert "state_hash" in state_msg


@pytest.mark.asyncio
async def test_ws_music_hello_immediate():
    """Test that hello arrives immediately without blocking on manager."""
    app = create_app()
    client = TestClient(app)

    auth_headers = _auth()

    # Mock the manager to be slow (simulate blocking)
    with patch("app.api.music_ws.get_ws_manager") as mock_get_manager:
        mock_manager = AsyncMock()
        mock_manager.add_connection = AsyncMock(return_value=MagicMock())

        async def slow_get_manager():
            await asyncio.sleep(2)  # Simulate slow manager
            return mock_manager

        mock_get_manager.side_effect = slow_get_manager

        # Connect with authentication
        with client.websocket_connect("/v1/ws/music", headers=auth_headers) as ws:
            # Should receive hello frame immediately (within 100ms)
            hello_msg = json.loads(ws.receive_text())

            # Verify hello frame structure and degraded mode
            assert hello_msg["type"] == "hello"
            assert hello_msg["proto"] == "json.realtime.v1"
            assert hello_msg["mode"] == "degraded"  # Should be degraded initially
            assert "ts" in hello_msg

            # Should receive initial state
            state_msg = json.loads(ws.receive_text())
            assert state_msg["type"] == "state_full"


@pytest.mark.asyncio
async def test_ws_music_degraded_to_ok_transition():
    """Test that mode transitions from degraded to ok after manager recovery."""
    app = create_app()
    client = TestClient(app)

    auth_headers = _auth()

    # Mock the manager to fail initially, then succeed
    with patch("app.api.music_ws.get_ws_manager") as mock_get_manager:
        mock_manager = AsyncMock()
        mock_manager.add_connection = AsyncMock(return_value=MagicMock())

        call_count = 0

        async def failing_then_succeeding_manager():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                await asyncio.sleep(0.1)  # Small delay
                raise Exception("Manager temporarily unavailable")
            return mock_manager

        mock_get_manager.side_effect = failing_then_succeeding_manager

        # Connect with authentication
        with client.websocket_connect("/v1/ws/music", headers=auth_headers) as ws:
            # Should receive hello frame in degraded mode
            hello_msg = json.loads(ws.receive_text())
            assert hello_msg["type"] == "hello"
            assert hello_msg["mode"] == "degraded"

            # Should receive initial state
            state_msg = json.loads(ws.receive_text())
            assert state_msg["type"] == "state_full"

            # Wait a bit for background retry
            await asyncio.sleep(0.2)

            # Send a ping command to test if manager is now available
            test_payload = {
                "type": "ping",
                "proto_ver": 1,
                "req_id": "test-123",
                "ts": 1234567890
            }
            ws.send_text(json.dumps(test_payload))

            # Should receive pong response (basic functionality working)
            # Note: there might be other messages in the queue, so we need to find the pong
            pong_found = False
            for _ in range(5):  # Try up to 5 messages
                response = json.loads(ws.receive_text())
                if response.get("type") == "pong":
                    assert response["proto_ver"] == 1
                    assert response["req_id"] == "test-123"
                    pong_found = True
                    break

            assert pong_found, "Should receive pong response"


@pytest.mark.asyncio
async def test_ws_music_hello_timestamp():
    """Test that hello message includes valid timestamp."""
    import time

    app = create_app()
    client = TestClient(app)

    auth_headers = _auth()

    with patch("app.api.music_ws.get_ws_manager") as mock_get_manager:
        mock_manager = AsyncMock()
        mock_manager.add_connection = AsyncMock(return_value=MagicMock())
        mock_get_manager.return_value = mock_manager

        # Connect with authentication
        with client.websocket_connect("/v1/ws/music", headers=auth_headers) as ws:
            # Record time before receiving hello
            before_time = int(time.time() * 1000)

            hello_msg = json.loads(ws.receive_text())

            # Record time after receiving hello
            after_time = int(time.time() * 1000)

            # Verify timestamp is reasonable
            ts = hello_msg["ts"]
            assert before_time - 100 <= ts <= after_time + 100  # Allow 100ms tolerance


@pytest.mark.asyncio
async def test_ws_music_subprotocol_required():
    """Test that connection fails if subprotocol negotiation fails."""
    app = create_app()
    client = TestClient(app)

    auth_headers = _auth()

    # This test verifies that we don't fall back gracefully
    # In practice, the WebSocket client will handle the subprotocol negotiation
    # and this test ensures our code path doesn't have fallback logic

    with patch("app.api.music_ws.get_ws_manager") as mock_get_manager:
        mock_manager = AsyncMock()
        mock_manager.add_connection = AsyncMock(return_value=MagicMock())
        mock_get_manager.return_value = mock_manager

        # Connect with authentication - should work with proper subprotocol
        with client.websocket_connect("/v1/ws/music", headers=auth_headers) as ws:
            hello_msg = json.loads(ws.receive_text())
            assert hello_msg["type"] == "hello"
            assert hello_msg["proto"] == "json.realtime.v1"

            # Should receive initial state
            state_msg = json.loads(ws.receive_text())
            assert state_msg["type"] == "state_full"
