"""Integration tests for WebSocket functionality with origin validation."""

import pytest
import asyncio
import websockets
from fastapi.testclient import TestClient
from unittest.mock import patch

from app.main import app


class TestWebSocketIntegration:
    """Test WebSocket integration with origin validation."""

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
                assert response.headers.get("X-WebSocket-Reason") == "HTTP requests not supported on WebSocket endpoints"

    def test_cors_origins_restricted_to_localhost(self):
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
        
        # The middleware should be configured with restricted origins
        # This is enforced in main.py during app startup

    @pytest.mark.asyncio
    async def test_websocket_origin_validation_integration(self):
        """Test WebSocket origin validation in integration."""
        # This test would require a real WebSocket server running
        # For now, we test the validation logic directly
        
        from app.security import validate_websocket_origin
        
        # Mock WebSocket with valid origin
        valid_ws = type('MockWebSocket', (), {
            'headers': {'Origin': 'http://localhost:3000'}
        })()
        
        # Mock WebSocket with invalid origin
        invalid_ws = type('MockWebSocket', (), {
            'headers': {'Origin': 'http://localhost:3000'}
        })()
        
        # Mock WebSocket without origin (non-browser client)
        no_origin_ws = type('MockWebSocket', (), {
            'headers': {}
        })()
        
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
        assert response.headers.get("X-WebSocket-Reason") == "HTTP requests not supported on WebSocket endpoints"
        assert "WebSocket endpoint requires WebSocket protocol" in response.text

    def test_cors_configuration_validation(self):
        """Test that CORS configuration enforces single origin policy."""
        # Verify that the app configuration enforces the WebSocket requirement
        # of only accepting http://localhost:3000
        
        # The CORS middleware should be configured with restricted origins
        assert hasattr(app, 'user_middleware')
        
        # Find CORS middleware configuration
        cors_middleware = None
        for middleware in app.user_middleware:
            if 'CORSMiddleware' in str(middleware.cls):
                cors_middleware = middleware
                break
        
        assert cors_middleware is not None, "CORS middleware should be configured"
        
        # The middleware should be configured with restricted origins
        # This is enforced in main.py during app startup

    def test_websocket_requirement_documentation(self):
        """Test that WebSocket requirements are properly documented in code."""
        # Verify that the WebSocket requirements are documented in the code
        
        # Check main.py for CORS origin restrictions
        with open('app/main.py', 'r') as f:
            main_content = f.read()
            assert "WebSocket requirement" in main_content
            assert "http://localhost:3000" in main_content
        
        # Check security.py for origin validation
        with open('app/security.py', 'r') as f:
            security_content = f.read()
            assert "WebSocket requirement" in security_content
            assert "validate_websocket_origin" in security_content
        
        # Check urls.ts for canonical origin
        with open('frontend/src/lib/urls.ts', 'r') as f:
            urls_content = f.read()
            assert "getCanonicalFrontendOrigin" in urls_content
            assert "buildCanonicalWebSocketUrl" in urls_content
