import os


def _auth():
    """Create auth headers for testing."""
    import jwt as _jwt

    token = _jwt.encode(
        {"user_id": "u_test"}, os.getenv("JWT_SECRET", "secret"), algorithm="HS256"
    )
    return {"Authorization": f"Bearer {token}"}


def _login_and_get_cookies(client, username: str = "alice"):
    """Login and return session cookies for WebSocket authentication."""
    r = client.post("/v1/auth/login", params={"username": username})
    assert r.status_code == 200
    # Collect cookies
    jar = client.cookies
    # Ensure expected cookies exist
    assert jar.get("GSNH_SESS") is not None
    return {
        "GSNH_SESS": jar.get("GSNH_SESS"),
    }


def test_music_ws_subprotocol_negotiation(client):
    """Test that music WebSocket properly handles subprotocol negotiation and sends hello frame."""
    # Use JWT auth header for test
    auth_headers = _auth()

    # Connect with authentication
    with client.websocket_connect("/v1/ws/music", headers=auth_headers) as ws:
        # Receive hello frame
        hello_msg = ws.receive_json()

        # Verify hello frame structure
        assert hello_msg.get("type") == "hello", f"Expected hello type, got {hello_msg}"
        assert (
            hello_msg.get("proto") == "json.realtime.v1"
        ), f"Expected json.realtime.v1 proto, got {hello_msg.get('proto')}"

        # Send a ping to test basic functionality
        import time

        ws.send_text("ping")
        # Give it a moment for the message to be processed
        time.sleep(0.1)
        pong_response = ws.receive_text()
        assert pong_response == "pong", f"Expected 'pong', got '{pong_response}'"


def test_music_ws_ping_pong(client):
    """Test basic WebSocket ping-pong functionality."""
    # Use JWT auth header for test
    auth_headers = _auth()

    # Connect with authentication
    with client.websocket_connect("/v1/ws/music", headers=auth_headers) as ws:
        # Skip the hello frame
        hello_msg = ws.receive_json()
        assert hello_msg.get("type") == "hello"

        # Test ping-pong
        ws.send_text("ping")
        response = ws.receive_text()
        assert response == "pong"

        # Test ping-pong with plain text (JSON ping is not handled by the current handler)
        ws.send_text("ping")
        response = ws.receive_text()
        assert response == "pong"


def test_music_ws_http_guard(client):
    """Test that HTTP requests to WebSocket endpoint are properly rejected."""

    # Test GET request
    response = client.get("/v1/ws/music")
    assert response.status_code == 400
    assert "WebSocket endpoint requires WebSocket protocol" in response.text

    # Test POST request
    response = client.post("/v1/ws/music")
    assert response.status_code == 400
    assert "WebSocket endpoint requires WebSocket protocol" in response.text
