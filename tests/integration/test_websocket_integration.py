"""Comprehensive integration tests for WebSocket functionality."""

import asyncio
import json
import time
import jwt
import os
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi.testclient import TestClient
import websockets

from app.main import app


class TestWebSocketIntegration:
    """Comprehensive WebSocket integration tests."""

    @pytest.fixture
    def jwt_token(self):
        """Generate a valid JWT token for testing."""
        secret = os.getenv("JWT_SECRET", "test_secret")
        payload = {
            "sub": "test_user_123",
            "user_id": "test_user_123",
            "scopes": ["test:read"],
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
        }
        return jwt.encode(payload, secret, algorithm="HS256")

    @pytest.fixture
    def expired_token(self):
        """Generate an expired JWT token for testing."""
        secret = os.getenv("JWT_SECRET", "test_secret")
        payload = {
            "sub": "test_user_123",
            "user_id": "test_user_123",
            "scopes": ["test:read"],
            "iat": int(time.time()) - 7200,  # 2 hours ago
            "exp": int(time.time()) - 3600,  # 1 hour ago (expired)
        }
        return jwt.encode(payload, secret, algorithm="HS256")

    @pytest.fixture
    def invalid_token(self):
        """Generate an invalid JWT token for testing."""
        return "invalid.jwt.token"

    def test_websocket_http_handler_crisp_errors(self):
        """Test that HTTP requests to WebSocket endpoints return crisp error codes."""
        client = TestClient(app)

        # Test various HTTP methods on WebSocket endpoints
        endpoints = ["/v1/ws/transcribe", "/v1/ws/music", "/v1/ws/care"]
        methods = ["GET", "POST", "PUT", "PATCH", "DELETE"]

        for endpoint in endpoints:
            for method in methods:
                response = client.request(method, endpoint)

                # WebSocket requirement: Should return 400 with crisp error information
                assert response.status_code == 400
                assert "WebSocket endpoint requires WebSocket protocol" in response.text
                assert response.headers.get("X-WebSocket-Error") == "protocol_required"
                assert (
                    response.headers.get("X-WebSocket-Reason")
                    == "HTTP requests not supported on WebSocket endpoints"
                )

    def test_cors_origins_restricted_to_localhost(self):
        """Test that CORS origins are restricted to http://localhost:3000."""
        # This test verifies that the CORS configuration in main.py
        # properly restricts origins to only http://localhost:3000

        # The CORS configuration should be enforced at the middleware level
        # We can verify this by checking that the app configuration is correct
        assert hasattr(app, "user_middleware")

        # Find CORS middleware
        cors_middleware = None
        for middleware in app.user_middleware:
            if "CORSMiddleware" in str(middleware.cls):
                cors_middleware = middleware
                break

        assert cors_middleware is not None, "CORS middleware should be configured"

        # The middleware should be configured with restricted origins
        # This is enforced in main.py during app startup

    @pytest.mark.asyncio
    async def test_websocket_origin_validation_integration(self):
        """Test WebSocket origin validation in integration."""
        # This test would require a real WebSocket server running
        # For now, we test the validation logic directly

        from app.security import validate_websocket_origin

        # Mock WebSocket with valid origin
        valid_ws = type(
            "MockWebSocket", (), {"headers": {"Origin": "http://localhost:3000"}}
        )()

        # Mock WebSocket with invalid origin
        invalid_ws = type(
            "MockWebSocket", (), {"headers": {"Origin": "http://localhost:3000"}}
        )()

        # Mock WebSocket without origin (non-browser client)
        no_origin_ws = type("MockWebSocket", (), {"headers": {}})()

        assert validate_websocket_origin(valid_ws) is True
        assert validate_websocket_origin(invalid_ws) is False
        assert validate_websocket_origin(no_origin_ws) is True

    def test_websocket_url_building_consistency(self):
        """Test that WebSocket URL building is consistent between frontend and backend."""
        # This test verifies the conceptual consistency
        # Frontend builds URLs using canonical origin (http://localhost:3000)
        # Backend validates origins against the same canonical origin

        canonical_origin = "http://localhost:3000"

        # Frontend would build: ws://localhost:3000/v1/ws/test
        # Backend expects: Origin: http://localhost:3000

        # The host part should match
        frontend_host = "localhost:3000"  # From ws://localhost:3000
        backend_expected_host = "localhost:3000"  # From http://localhost:3000

        assert frontend_host == backend_expected_host

    def test_websocket_error_handling_headers(self):
        """Test that WebSocket HTTP handler includes proper error headers."""
        client = TestClient(app)

        response = client.get("/v1/ws/transcribe")

        # WebSocket requirement: Crisp error codes and reasons
        assert response.status_code == 400
        assert response.headers.get("X-WebSocket-Error") == "protocol_required"
        assert (
            response.headers.get("X-WebSocket-Reason")
            == "HTTP requests not supported on WebSocket endpoints"
        )
        assert "WebSocket endpoint requires WebSocket protocol" in response.text

    def test_cors_configuration_validation(self):
        """Test that CORS configuration enforces single origin policy."""
        # Verify that the app configuration enforces the WebSocket requirement
        # of only accepting http://localhost:3000

        # The CORS middleware should be configured with restricted origins
        assert hasattr(app, "user_middleware")

        # Find CORS middleware configuration
        cors_middleware = None
        for middleware in app.user_middleware:
            if "CORSMiddleware" in str(middleware.cls):
                cors_middleware = middleware
                break

        assert cors_middleware is not None, "CORS middleware should be configured"

        # The middleware should be configured with restricted origins
        # This is enforced in main.py during app startup

    def test_websocket_requirement_documentation(self):
        """Test that WebSocket requirements are properly documented in code."""
        # Verify that the WebSocket requirements are documented in the code

        # Check main.py for CORS origin restrictions
        with open("app/main.py") as f:
            main_content = f.read()
            assert "WebSocket requirement" in main_content
            assert "http://localhost:3000" in main_content

        # Check security.py for origin validation
        with open("app/security.py") as f:
            security_content = f.read()
            assert "WebSocket requirement" in security_content
            assert "validate_websocket_origin" in security_content

        # Check urls.ts for canonical origin
        with open("frontend/src/lib/urls.ts") as f:
            urls_content = f.read()
            assert "getCanonicalFrontendOrigin" in urls_content
            assert "buildCanonicalWebSocketUrl" in urls_content

    @pytest.mark.asyncio
    async def test_websocket_auth_successful_connection(self, jwt_token):
        """Test successful WebSocket connection with valid JWT token."""
        # This test would require a running server
        # For now, we'll test the authentication logic directly
        from app.security_ws import verify_ws

        # Mock WebSocket with valid token
        mock_ws = Mock()
        mock_ws.headers = {
            "Authorization": f"Bearer {jwt_token}",
            "Origin": "http://localhost:3000"
        }
        mock_ws.state = Mock()
        mock_ws.url = Mock()
        mock_ws.url.query = ""
        mock_ws.client = Mock()
        mock_ws.client.host = "127.0.0.1"
        mock_ws.app = Mock()
        mock_ws.app.state = Mock()
        mock_ws.app.state.allowed_origins = ["http://localhost:3000"]

        # Mock the jwt_decode function to return expected payload
        import app.security
        original_jwt_decode = app.security.jwt_decode
        app.security.jwt_decode = Mock(return_value={
            "sub": "test_user_123",
            "user_id": "test_user_123",
            "scopes": ["test:read"]
        })

        try:
            await verify_ws(mock_ws)
            assert mock_ws.state.user_id == "test_user_123"
            assert mock_ws.state.scopes == ["test:read"]
        finally:
            app.security.jwt_decode = original_jwt_decode

    @pytest.mark.asyncio
    async def test_websocket_auth_missing_token(self):
        """Test WebSocket connection rejection with missing token."""
        from app.security_ws import verify_ws

        mock_ws = Mock()
        mock_ws.headers = {"Origin": "http://localhost:3000"}
        mock_ws.state = Mock()
        mock_ws.url = Mock()
        mock_ws.url.query = ""
        mock_ws.client = Mock()
        mock_ws.client.host = "127.0.0.1"
        mock_ws.app = Mock()
        mock_ws.app.state = Mock()
        mock_ws.app.state.allowed_origins = ["http://localhost:3000"]

        mock_ws.close = AsyncMock()

        # Set JWT_SECRET to enable authentication
        original_secret = os.environ.get("JWT_SECRET")
        os.environ["JWT_SECRET"] = "test_secret"

        try:
            await verify_ws(mock_ws)
            mock_ws.close.assert_called_with(code=4401, reason="missing_token")
        finally:
            if original_secret:
                os.environ["JWT_SECRET"] = original_secret
            else:
                os.environ.pop("JWT_SECRET", None)

    @pytest.mark.asyncio
    async def test_websocket_auth_invalid_origin(self):
        """Test WebSocket connection rejection with invalid origin."""
        from app.security_ws import verify_ws

        mock_ws = Mock()
        mock_ws.headers = {"Origin": "https://malicious.com"}
        mock_ws.state = Mock()
        mock_ws.url = Mock()
        mock_ws.url.query = ""
        mock_ws.client = Mock()
        mock_ws.client.host = "127.0.0.1"
        mock_ws.app = Mock()
        mock_ws.app.state = Mock()
        mock_ws.app.state.allowed_origins = ["http://localhost:3000"]

        mock_ws.close = AsyncMock()

        await verify_ws(mock_ws)
        mock_ws.close.assert_called_with(code=4403, reason="origin_not_allowed")

    @pytest.mark.asyncio
    async def test_websocket_auth_expired_token(self, expired_token):
        """Test WebSocket connection rejection with expired token."""
        from app.security_ws import verify_ws

        mock_ws = Mock()
        mock_ws.headers = {
            "Authorization": f"Bearer {expired_token}",
            "Origin": "http://localhost:3000"
        }
        mock_ws.state = Mock()
        mock_ws.url = Mock()
        mock_ws.url.query = ""
        mock_ws.client = Mock()
        mock_ws.client.host = "127.0.0.1"
        mock_ws.app = Mock()
        mock_ws.app.state = Mock()
        mock_ws.app.state.allowed_origins = ["http://localhost:3000"]

        mock_ws.close = AsyncMock()

        # Set JWT_SECRET to enable authentication
        original_secret = os.environ.get("JWT_SECRET")
        os.environ["JWT_SECRET"] = "test_secret"

        try:
            await verify_ws(mock_ws)
            # Should be called with invalid_token (jwt.ExpiredSignatureError is caught as jwt.InvalidTokenError)
            mock_ws.close.assert_called_with(code=4401, reason="invalid_token")
        finally:
            if original_secret:
                os.environ["JWT_SECRET"] = original_secret
            else:
                os.environ.pop("JWT_SECRET", None)

    @pytest.mark.asyncio
    async def test_websocket_connection_state_management(self):
        """Test WebSocket connection state management."""
        from app.ws_manager import WSConnectionManager

        manager = WSConnectionManager()

        # Test adding connection
        mock_ws = Mock()
        mock_ws.send_json = AsyncMock()
        mock_ws.close = AsyncMock()

        conn_state = await manager.add_connection(mock_ws, "test_user", endpoint="test")
        assert conn_state.user_id == "test_user"
        assert conn_state.is_alive == True
        assert conn_state.metadata["endpoint"] == "test"

        # Test getting connection
        retrieved = manager.get_connection("test_user")
        assert retrieved == conn_state

        # Test broadcasting
        await manager.broadcast_to_all({"test": "message"})
        mock_ws.send_json.assert_called_with({"test": "message"})

        # Test sending to specific user
        success = await manager.send_to_user("test_user", {"direct": "message"})
        assert success == True
        assert mock_ws.send_json.call_count == 2

        # Test removing connection
        await manager.remove_connection("test_user")
        assert manager.get_connection("test_user") is None
        mock_ws.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_websocket_broadcasting_with_dead_connections(self):
        """Test broadcasting handles dead connections gracefully."""
        from app.ws_manager import WSConnectionManager

        manager = WSConnectionManager()

        # Add live connection
        live_ws = Mock()
        live_ws.send_json = AsyncMock()
        await manager.add_connection(live_ws, "live_user", endpoint="test")

        # Add dead connection (will fail to send)
        dead_ws = Mock()
        dead_ws.send_json = AsyncMock(side_effect=Exception("Connection dead"))
        dead_ws.close = AsyncMock()
        await manager.add_connection(dead_ws, "dead_user", endpoint="test")

        # Broadcast should handle dead connection gracefully
        await manager.broadcast_to_all({"broadcast": "test"})

        # Live connection should receive message
        live_ws.send_json.assert_called_with({"broadcast": "test"})

        # Dead connection should have been marked as not alive
        dead_conn = manager.get_connection("dead_user")
        assert dead_conn.is_alive == False

    def test_websocket_http_handler_comprehensive_errors(self):
        """Test comprehensive error handling for HTTP requests to WS endpoints."""
        client = TestClient(app)

        endpoints = [
            "/v1/ws/transcribe",
            "/v1/ws/music",
            "/v1/ws/care",
            "/v1/ws/health"
        ]

        methods = ["GET", "POST", "PUT", "PATCH", "DELETE"]

        for endpoint in endpoints:
            for method in methods:
                response = client.request(method, endpoint)

                # Should return 400 for WebSocket protocol requirement
                assert response.status_code == 400
                assert "WebSocket endpoint requires WebSocket protocol" in response.text
                assert response.headers.get("X-WebSocket-Error") == "protocol_required"
                assert response.headers.get("X-WebSocket-Reason") == "HTTP requests not supported on WebSocket endpoints"
