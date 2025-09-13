"""
WebSocket Music State and Delta Tests

Tests state synchronization and delta emission:
- Connect → hello + initial state
- Play → state changes and deltas flow
- Pause → position ticks slow down
- State hash updates correctly
"""

import json
import os
import time

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
async def test_ws_music_connect_hello_state():
    """Test WebSocket connects, receives hello, then initial state."""
    app = create_app()
    client = TestClient(app)

    auth_headers = _auth()

    with client.websocket_connect("/v1/ws/music", headers=auth_headers) as ws:
        # Should receive hello message first
        hello_msg = json.loads(ws.receive_text())
        assert hello_msg["type"] == "hello"
        assert hello_msg["proto"] == "json.realtime.v1"
        assert "mode" in hello_msg
        assert "ts" in hello_msg

        # Should receive initial state delta
        state_msg = json.loads(ws.receive_text())
        assert state_msg["type"] in ["state_full", "state_delta"]
        assert "state" in state_msg
        assert "state_hash" in state_msg

        state = state_msg["state"]
        assert "is_playing" in state
        assert "progress_ms" in state
        assert "provider" in state
        assert state["provider"] == "fake"


@pytest.mark.asyncio
async def test_ws_music_play_deltas():
    """Test that playing triggers state changes and deltas."""
    app = create_app()
    client = TestClient(app)

    auth_headers = _auth()

    with client.websocket_connect("/v1/ws/music", headers=auth_headers) as ws:
        # Skip hello and initial state
        ws.receive_text()  # hello
        ws.receive_text()  # initial state

        # Send play command
        play_payload = {
            "type": "play",
            "proto_ver": 1,
            "req_id": "play-test-123",
            "entity_id": "track1",
            "entity_type": "track",
        }
        ws.send_text(json.dumps(play_payload))

        # Should receive ack
        ack_msg = json.loads(ws.receive_text())
        assert ack_msg["type"] == "ack"
        assert ack_msg["req_id"] == "play-test-123"

        # Should receive state delta for the play action
        delta_msg = json.loads(ws.receive_text())
        assert delta_msg["type"] == "state_delta"
        assert "state" in delta_msg
        assert delta_msg["state"]["is_playing"] is True


@pytest.mark.asyncio
async def test_ws_music_pause_ticks_slow():
    """Test that pause slows down position ticks."""
    app = create_app()
    client = TestClient(app)

    auth_headers = _auth()

    with client.websocket_connect("/v1/ws/music", headers=auth_headers) as ws:
        # Skip hello and initial state
        ws.receive_text()  # hello
        ws.receive_text()  # initial state

        # Start playing
        play_payload = {
            "type": "play",
            "proto_ver": 1,
            "req_id": "play-test-123",
            "entity_id": "track1",
            "entity_type": "track",
        }
        ws.send_text(json.dumps(play_payload))
        ws.receive_text()  # ack
        ws.receive_text()  # state delta

        # Wait for a position tick (should come quickly when playing)
        start_time = time.time()
        tick_received = False

        # Set a timeout for receiving ticks
        timeout = 3.0  # Should receive tick within 3 seconds when playing
        end_time = start_time + timeout

        while time.time() < end_time:
            try:
                msg = json.loads(ws.receive_text())
                if msg["type"] == "position_tick":
                    tick_received = True
                    playing_tick_time = time.time()
                    break
            except:
                pass

        assert tick_received, "Should receive position tick when playing"

        # Now pause
        pause_payload = {"type": "pause", "proto_ver": 1, "req_id": "pause-test-123"}
        ws.send_text(json.dumps(pause_payload))
        ws.receive_text()  # ack
        ws.receive_text()  # state delta

        # Wait for next position tick (should be slower when paused)
        tick_received_after_pause = False
        pause_start_time = time.time()
        pause_timeout = 12.0  # Should NOT receive tick within 12 seconds when paused

        while time.time() < pause_start_time + pause_timeout:
            try:
                msg = json.loads(ws.receive_text())
                if msg["type"] == "position_tick":
                    tick_received_after_pause = True
                    break
            except:
                pass

        # Should not receive tick quickly when paused
        assert (
            not tick_received_after_pause
        ), "Should not receive position tick quickly when paused"


@pytest.mark.asyncio
async def test_ws_music_state_hash_updates():
    """Test that state hash updates correctly on state changes."""
    app = create_app()
    client = TestClient(app)

    auth_headers = _auth()

    with client.websocket_connect("/v1/ws/music", headers=auth_headers) as ws:
        # Skip hello
        ws.receive_text()  # hello

        # Get initial state
        initial_state_msg = json.loads(ws.receive_text())
        initial_hash = initial_state_msg["state_hash"]

        # Play a track
        play_payload = {
            "type": "play",
            "proto_ver": 1,
            "req_id": "play-test-123",
            "entity_id": "track1",
            "entity_type": "track",
        }
        ws.send_text(json.dumps(play_payload))
        ws.receive_text()  # ack

        # Get state after playing
        play_state_msg = json.loads(ws.receive_text())
        play_hash = play_state_msg["state_hash"]

        # Hash should be different after state change
        assert play_hash != initial_hash

        # Pause
        pause_payload = {"type": "pause", "proto_ver": 1, "req_id": "pause-test-123"}
        ws.send_text(json.dumps(pause_payload))
        ws.receive_text()  # ack

        # Get state after pausing
        pause_state_msg = json.loads(ws.receive_text())
        pause_hash = pause_state_msg["state_hash"]

        # Hash should be different after pause
        assert pause_hash != play_hash


@pytest.mark.asyncio
async def test_ws_music_refresh_state():
    """Test refreshState command returns current state."""
    app = create_app()
    client = TestClient(app)

    auth_headers = _auth()

    with client.websocket_connect("/v1/ws/music", headers=auth_headers) as ws:
        # Skip hello and initial state
        ws.receive_text()  # hello
        ws.receive_text()  # initial state

        # Send refreshState command
        refresh_payload = {
            "type": "refreshState",
            "proto_ver": 1,
            "req_id": "refresh-test-123",
        }
        ws.send_text(json.dumps(refresh_payload))

        # Should receive state response
        response = json.loads(ws.receive_text())
        assert response["type"] == "state"
        assert response["req_id"] == "refresh-test-123"
        assert "data" in response
        assert "state_hash" in response

        state_data = response["data"]
        assert "is_playing" in state_data
        assert "progress_ms" in state_data
        assert "provider" in state_data


@pytest.mark.asyncio
async def test_ws_music_multiple_commands():
    """Test multiple commands and their effects on state."""
    app = create_app()
    client = TestClient(app)

    auth_headers = _auth()

    with client.websocket_connect("/v1/ws/music", headers=auth_headers) as ws:
        # Skip hello and initial state
        ws.receive_text()  # hello
        ws.receive_text()  # initial state

        # Play track
        play_payload = {
            "type": "play",
            "proto_ver": 1,
            "req_id": "play-test-123",
            "entity_id": "track1",
            "entity_type": "track",
        }
        ws.send_text(json.dumps(play_payload))
        ws.receive_text()  # ack
        play_state = json.loads(ws.receive_text())  # state delta
        assert play_state["state"]["is_playing"] is True

        # Set volume
        volume_payload = {
            "type": "setVolume",
            "proto_ver": 1,
            "req_id": "volume-test-123",
            "level": 75,
        }
        ws.send_text(json.dumps(volume_payload))
        ws.receive_text()  # ack
        volume_state = json.loads(ws.receive_text())  # state delta
        assert volume_state["state"]["volume_percent"] == 75

        # Seek to position
        seek_payload = {
            "type": "seek",
            "proto_ver": 1,
            "req_id": "seek-test-123",
            "position_ms": 60000,
        }
        ws.send_text(json.dumps(seek_payload))
        ws.receive_text()  # ack
        seek_state = json.loads(ws.receive_text())  # state delta
        assert seek_state["state"]["progress_ms"] == 60000
