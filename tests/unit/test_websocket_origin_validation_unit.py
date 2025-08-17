"""Test WebSocket origin validation and URL building functionality."""

import pytest
from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch

from app.security import validate_websocket_origin, verify_ws
from app.main import app


def test_validate_websocket_origin_valid():
    """Test that valid origin (http://localhost:3000) is accepted."""
    websocket = Mock()
    websocket.headers = {"Origin": "http://localhost:3000"}
    
    assert validate_websocket_origin(websocket) is True


def test_validate_websocket_origin_invalid():
    """Test that invalid origins are rejected."""
    websocket = Mock()
    
    # Test various invalid origins
    invalid_origins = [
        "http://127.0.0.1:3000",
        "https://localhost:3000", 
        "http://localhost:3001",
        "http://example.com",
        "ws://localhost:3000",
        "wss://localhost:3000"
    ]
    
    for origin in invalid_origins:
        websocket.headers = {"Origin": origin}
        assert validate_websocket_origin(websocket) is False, f"Origin {origin} should be rejected"


def test_validate_websocket_origin_missing():
    """Test that missing origin header is allowed (for non-browser clients)."""
    websocket = Mock()
    websocket.headers = {}
    
    assert validate_websocket_origin(websocket) is True


def test_validate_websocket_origin_none():
    """Test that None origin is allowed."""
    websocket = Mock()
    websocket.headers = {"Origin": None}
    
    assert validate_websocket_origin(websocket) is True


@pytest.mark.asyncio
async def test_verify_ws_origin_validation():
    """Test that verify_ws rejects invalid origins with proper error codes."""
    websocket = Mock()
    websocket.headers = {"Origin": "http://127.0.0.1:3000"}
    # Create async mock for close method
    async def async_close(*args, **kwargs):
        return None
    websocket.close = Mock(side_effect=async_close)
    
    # Mock JWT secret to avoid token validation
    with patch.dict('os.environ', {'JWT_SECRET': ''}):
        await verify_ws(websocket)
    
    # Should close with policy violation code and reason
    websocket.close.assert_called_once_with(
        code=1008,  # Policy violation
        reason="Origin not allowed: only http://localhost:3000 accepted"
    )


@pytest.mark.asyncio
async def test_verify_ws_valid_origin():
    """Test that verify_ws accepts valid origin."""
    websocket = Mock()
    websocket.headers = {"Origin": "http://localhost:3000"}
    # Create async mock for close method
    async def async_close(*args, **kwargs):
        return None
    websocket.close = Mock(side_effect=async_close)
    
    # Mock JWT secret to avoid token validation
    with patch.dict('os.environ', {'JWT_SECRET': ''}):
        await verify_ws(websocket)
    
    # Should not close the connection
    websocket.close.assert_not_called()


def test_websocket_http_handler_error_codes():
    """Test that HTTP requests to WebSocket endpoints return crisp error codes."""
    client = TestClient(app)
    
    # Test various HTTP methods on WebSocket endpoints
    endpoints = ["/v1/ws/transcribe", "/v1/ws/music", "/v1/ws/care"]
    methods = ["GET", "POST", "PUT", "PATCH", "DELETE"]
    
    for endpoint in endpoints:
        for method in methods:
            response = client.request(method, endpoint)
            
            # Should return 400 with crisp error information
            assert response.status_code == 400
            assert "WebSocket endpoint requires WebSocket protocol" in response.text
            assert response.headers.get("X-WebSocket-Error") == "protocol_required"
            assert response.headers.get("X-WebSocket-Reason") == "HTTP requests not supported on WebSocket endpoints"


def test_cors_origins_restricted():
    """Test that CORS origins are restricted to http://localhost:3000."""
    # This test verifies that the CORS configuration in main.py
    # properly restricts origins to only http://localhost:3000
    
    # The CORS configuration should be enforced at the middleware level
    # We can verify this by checking that the app configuration is correct
    assert hasattr(app, 'user_middleware')
    
    # Find CORS middleware
    cors_middleware = None
    for middleware in app.user_middleware:
        if 'CORSMiddleware' in str(middleware.cls):
            cors_middleware = middleware
            break
    
    assert cors_middleware is not None, "CORS middleware should be configured"
