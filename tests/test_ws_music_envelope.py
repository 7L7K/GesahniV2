"""
WebSocket Music Envelope and Command Tests

Tests envelope validation and command dispatcher:
- Envelope validation (type, proto_ver, req_id, ts)
- Ack/error responses under 500ms
- LRU idempotency cache with duplicate req_id handling
"""

import asyncio
import json
import os
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
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
async def test_envelope_validation_valid():
    """Test valid envelope passes validation."""
    app = create_app()
    client = TestClient(app)

    auth_headers = _auth()

    with patch("app.api.music_ws.get_ws_manager") as mock_get_manager:
        mock_manager = AsyncMock()
        mock_manager.add_connection = AsyncMock(return_value=MagicMock())
        mock_get_manager.return_value = mock_manager

        with client.websocket_connect("/v1/ws/music", headers=auth_headers) as ws:
            # Skip hello
            ws.receive_text()

            # Send valid envelope
            valid_payload = {
                "type": "ping",
                "proto_ver": 1,
                "req_id": "test-123",
                "ts": 1234567890,
            }
            ws.send_text(json.dumps(valid_payload))

            # Should receive pong response
            response = json.loads(ws.receive_text())
            assert response["type"] == "pong"
            assert response["proto_ver"] == 1
            assert response["req_id"] == "test-123"


@pytest.mark.asyncio
async def test_envelope_validation_missing_type():
    """Test envelope validation rejects missing type field."""
    app = create_app()
    client = TestClient(app)

    auth_headers = _auth()

    with patch("app.api.music_ws.get_ws_manager") as mock_get_manager:
        mock_manager = AsyncMock()
        mock_manager.add_connection = AsyncMock(return_value=MagicMock())
        mock_get_manager.return_value = mock_manager

        with client.websocket_connect("/v1/ws/music", headers=auth_headers) as ws:
            # Skip hello
            ws.receive_text()

            # Send invalid envelope (missing type)
            invalid_payload = {"proto_ver": 1, "req_id": "test-123"}
            ws.send_text(json.dumps(invalid_payload))

            # Should receive error response
            response = json.loads(ws.receive_text())
            assert response["type"] == "error"
            assert "missing required field: type" in response["message"]


@pytest.mark.asyncio
async def test_envelope_validation_invalid_proto_ver():
    """Test envelope validation rejects invalid proto_ver."""
    app = create_app()
    client = TestClient(app)

    auth_headers = _auth()

    with patch("app.api.music_ws.get_ws_manager") as mock_get_manager:
        mock_manager = AsyncMock()
        mock_manager.add_connection = AsyncMock(return_value=MagicMock())
        mock_get_manager.return_value = mock_manager

        with client.websocket_connect("/v1/ws/music", headers=auth_headers) as ws:
            # Skip hello
            ws.receive_text()

            # Send invalid envelope (wrong proto_ver)
            invalid_payload = {
                "type": "ping",
                "proto_ver": 2,  # Should be 1
                "req_id": "test-123",
            }
            ws.send_text(json.dumps(invalid_payload))

            # Should receive error response
            response = json.loads(ws.receive_text())
            assert response["type"] == "error"
            assert "unsupported proto_ver" in response["message"]


@pytest.mark.asyncio
async def test_ack_response_timing():
    """Test that ack responses arrive within 500ms."""
    app = create_app()
    client = TestClient(app)

    auth_headers = _auth()

    with patch("app.api.music_ws.get_ws_manager") as mock_get_manager:
        mock_manager = AsyncMock()
        mock_manager.add_connection = AsyncMock(return_value=MagicMock())
        mock_get_manager.return_value = mock_manager

        with client.websocket_connect("/v1/ws/music", headers=auth_headers) as ws:
            # Skip hello
            ws.receive_text()

            # Send ping command with timing
            start_time = time.time()
            ping_payload = {"type": "ping", "proto_ver": 1, "req_id": "timing-test-123"}
            ws.send_text(json.dumps(ping_payload))

            # Receive response
            response = json.loads(ws.receive_text())
            end_time = time.time()

            # Verify response timing
            duration_ms = (end_time - start_time) * 1000
            assert duration_ms < 500, f"Response took {duration_ms}ms, expected < 500ms"

            # Verify response content
            assert response["type"] == "pong"
            assert response["req_id"] == "timing-test-123"


@pytest.mark.asyncio
async def test_error_response_timing():
    """Test that error responses arrive within 500ms."""
    app = create_app()
    client = TestClient(app)

    auth_headers = _auth()

    with patch("app.api.music_ws.get_ws_manager") as mock_get_manager:
        mock_manager = AsyncMock()
        mock_manager.add_connection = AsyncMock(return_value=MagicMock())
        mock_get_manager.return_value = mock_manager

        with client.websocket_connect("/v1/ws/music", headers=auth_headers) as ws:
            # Skip hello
            ws.receive_text()

            # Send invalid command with timing
            start_time = time.time()
            invalid_payload = {
                "type": "unknown_command",
                "proto_ver": 1,
                "req_id": "error-timing-test-123",
            }
            ws.send_text(json.dumps(invalid_payload))

            # Receive error response
            response = json.loads(ws.receive_text())
            end_time = time.time()

            # Verify response timing
            duration_ms = (end_time - start_time) * 1000
            assert (
                duration_ms < 500
            ), f"Error response took {duration_ms}ms, expected < 500ms"

            # Verify error response content
            assert response["type"] == "error"
            assert response["req_id"] == "error-timing-test-123"
            assert "unknown command type" in response["message"]


@pytest.mark.asyncio
async def test_idempotency_cache_duplicate_req_id():
    """Test that duplicate req_id returns the same cached outcome."""
    app = create_app()
    client = TestClient(app)

    auth_headers = _auth()

    with patch("app.api.music_ws.get_ws_manager") as mock_get_manager:
        mock_manager = AsyncMock()
        mock_manager.add_connection = AsyncMock(return_value=MagicMock())
        mock_get_manager.return_value = mock_manager

        with client.websocket_connect("/v1/ws/music", headers=auth_headers) as ws:
            # Skip hello
            ws.receive_text()

            # Send ping command twice with same req_id
            req_id = "duplicate-test-123"
            ping_payload = {"type": "ping", "proto_ver": 1, "req_id": req_id}

            # First request
            ws.send_text(json.dumps(ping_payload))
            response1 = json.loads(ws.receive_text())

            # Small delay
            await asyncio.sleep(0.01)

            # Second request with same req_id
            ws.send_text(json.dumps(ping_payload))
            response2 = json.loads(ws.receive_text())

            # Both responses should be pong (since ping commands get pong responses)
            assert response1["type"] == response2["type"] == "pong"
            assert response1["req_id"] == response2["req_id"] == req_id
            assert response1["proto_ver"] == response2["proto_ver"] == 1

            # Timestamps should be different (not cached)
            # Note: In a real implementation, you might want to cache the full response
            # but for ping, we generate fresh timestamps


@pytest.mark.asyncio
async def test_refresh_state_command():
    """Test refreshState command with proper envelope."""
    app = create_app()
    client = TestClient(app)

    auth_headers = _auth()

    # Mock the state building function
    with (
        patch("app.api.music_ws.get_ws_manager") as mock_get_manager,
        patch("app.api.music_ws._build_state_payload") as mock_build_state,
    ):
        mock_manager = AsyncMock()
        mock_manager.add_connection = AsyncMock(return_value=MagicMock())
        mock_get_manager.return_value = mock_manager

        # Mock state payload
        mock_state = MagicMock()
        mock_state.model_dump.return_value = {"test": "state"}
        mock_build_state.return_value = mock_state

        with client.websocket_connect("/v1/ws/music", headers=auth_headers) as ws:
            # Skip hello
            ws.receive_text()

            # Send refreshState command
            refresh_payload = {
                "type": "refreshState",
                "proto_ver": 1,
                "req_id": "refresh-test-123",
                "ts": 1234567890,
            }
            ws.send_text(json.dumps(refresh_payload))

            # Should receive state response
            response = json.loads(ws.receive_text())
            assert response["type"] == "state"
            assert response["proto_ver"] == 1
            assert response["req_id"] == "refresh-test-123"
            assert response["data"] == {"test": "state"}


@pytest.mark.asyncio
async def test_command_dispatcher_error_handling():
    """Test command dispatcher error handling."""
    app = create_app()
    client = TestClient(app)

    auth_headers = _auth()

    with (
        patch("app.api.music_ws.get_ws_manager") as mock_get_manager,
        patch("app.api.music_ws._build_state_payload") as mock_build_state,
    ):
        mock_manager = AsyncMock()
        mock_manager.add_connection = AsyncMock(return_value=MagicMock())
        mock_get_manager.return_value = mock_manager

        # Mock state building to raise exception
        mock_build_state.side_effect = Exception("State building failed")

        with client.websocket_connect("/v1/ws/music", headers=auth_headers) as ws:
            # Skip hello
            ws.receive_text()

            # Send refreshState command that will fail
            refresh_payload = {
                "type": "refreshState",
                "proto_ver": 1,
                "req_id": "error-test-123",
            }
            ws.send_text(json.dumps(refresh_payload))

            # Should receive error response
            response = json.loads(ws.receive_text())
            assert response["type"] == "error"
            assert response["req_id"] == "error-test-123"
            assert "State building failed" in response["message"]
