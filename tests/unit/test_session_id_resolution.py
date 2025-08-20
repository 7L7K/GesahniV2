"""
Tests for centralized session ID resolution to ensure consistency across the codebase.
"""

import pytest
from unittest.mock import Mock
from fastapi import Request
from fastapi.testclient import TestClient

from app.deps.user import resolve_session_id, get_current_session_device


class TestResolveSessionId:
    """Test the centralized session ID resolution function."""

    def test_session_cookie_priority(self):
        """Test that __session cookie takes highest priority."""
        request = Mock(spec=Request)
        request.headers = {"X-Session-ID": "header_session_123"}
        request.cookies = {"__session": "sess_1234567890_abcdef12", "sid": "cookie_session_456"}
        
        result = resolve_session_id(request=request, user_id="user_789")
        
        assert result == "sess_1234567890_abcdef12"

    def test_session_cookie_opaque_validation(self):
        """Test that __session cookie must contain opaque session ID (not JWT)."""
        request = Mock(spec=Request)
        request.headers = {"X-Session-ID": "header_session_123"}
        request.cookies = {"__session": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"}
        
        result = resolve_session_id(request=request, user_id="user_789")
        
        # Should fall back to header since __session contains JWT
        assert result == "header_session_123"

    def test_session_cookie_legacy_name(self):
        """Test that legacy 'session' cookie name is supported."""
        request = Mock(spec=Request)
        request.headers = {"X-Session-ID": "header_session_123"}
        request.cookies = {"session": "sess_1234567890_abcdef12"}
        
        result = resolve_session_id(request=request, user_id="user_789")
        
        assert result == "sess_1234567890_abcdef12"

    def test_x_session_id_header_secondary_priority(self):
        """Test that X-Session-ID header takes secondary priority after __session cookie."""
        request = Mock(spec=Request)
        request.headers = {"X-Session-ID": "header_session_123"}
        request.cookies = {"sid": "cookie_session_456"}
        
        result = resolve_session_id(request=request, user_id="user_789")
        
        assert result == "header_session_123"

    def test_sid_cookie_fallback(self):
        """Test that sid cookie is used when higher priority sources are not present."""
        request = Mock(spec=Request)
        request.headers = {}
        request.cookies = {"sid": "cookie_session_456"}
        
        result = resolve_session_id(request=request, user_id="user_789")
        
        assert result == "cookie_session_456"

    def test_user_id_fallback(self):
        """Test that user_id is used when no session sources are present."""
        request = Mock(spec=Request)
        request.headers = {}
        request.cookies = {}
        
        result = resolve_session_id(request=request, user_id="user_789")
        
        assert result == "user_789"

    def test_anon_fallback(self):
        """Test that 'anon' is returned when no session ID sources are available."""
        request = Mock(spec=Request)
        request.headers = {}
        request.cookies = {}
        
        result = resolve_session_id(request=request, user_id=None)
        
        assert result == "anon"

    def test_anon_user_id_ignored(self):
        """Test that 'anon' user_id is ignored and falls back to 'anon'."""
        request = Mock(spec=Request)
        request.headers = {}
        request.cookies = {}
        
        result = resolve_session_id(request=request, user_id="anon")
        
        assert result == "anon"

    def test_websocket_session_cookie_priority(self):
        """Test that websocket __session cookie takes priority."""
        websocket = Mock()
        websocket.query_params = {"sid": "websocket_session_123"}
        websocket.headers = {"Cookie": "__session=sess_1234567890_abcdef12; sid=cookie_session_456"}
        
        result = resolve_session_id(websocket=websocket)
        
        assert result == "sess_1234567890_abcdef12"

    def test_websocket_session_cookie_opaque_validation(self):
        """Test that websocket __session cookie must contain opaque session ID (not JWT)."""
        websocket = Mock()
        websocket.query_params = {"sid": "websocket_session_123"}
        websocket.headers = {"Cookie": "__session=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"}
        
        result = resolve_session_id(websocket=websocket)
        
        # Should fall back to query param since __session contains JWT
        assert result == "websocket_session_123"

    def test_websocket_query_param_fallback(self):
        """Test that websocket query parameter is used when __session cookie is not present."""
        websocket = Mock()
        websocket.query_params = {"sid": "websocket_session_123"}
        websocket.headers = {}
        
        result = resolve_session_id(websocket=websocket)
        
        assert result == "websocket_session_123"

    def test_websocket_priority_over_user_id(self):
        """Test that websocket sources take priority over user_id."""
        websocket = Mock()
        websocket.query_params = {"sid": "websocket_session_123"}
        websocket.headers = {}
        
        result = resolve_session_id(websocket=websocket, user_id="user_789")
        
        assert result == "websocket_session_123"

    def test_request_priority_over_websocket(self):
        """Test that request sources take priority over websocket sources."""
        request = Mock(spec=Request)
        request.headers = {"X-Session-ID": "header_session_123"}
        request.cookies = {}
        
        websocket = Mock()
        websocket.query_params = {"sid": "websocket_session_456"}
        
        result = resolve_session_id(request=request, websocket=websocket)
        
        assert result == "header_session_123"

    def test_exception_handling_session_cookie(self):
        """Test that exceptions in __session cookie access are handled gracefully."""
        request = Mock(spec=Request)
        request.cookies.get.side_effect = Exception("Cookie access error")
        request.headers = {"X-Session-ID": "header_session_123"}
        
        result = resolve_session_id(request=request)
        
        assert result == "header_session_123"

    def test_exception_handling_header(self):
        """Test that exceptions in header access are handled gracefully."""
        request = Mock(spec=Request)
        request.headers.get.side_effect = Exception("Header access error")
        request.cookies = {"sid": "cookie_session_456"}
        
        result = resolve_session_id(request=request)
        
        assert result == "cookie_session_456"

    def test_exception_handling_cookie(self):
        """Test that exceptions in cookie access are handled gracefully."""
        request = Mock(spec=Request)
        request.headers = {}
        request.cookies.get.side_effect = Exception("Cookie access error")
        
        result = resolve_session_id(request=request, user_id="user_789")
        
        assert result == "user_789"

    def test_exception_handling_websocket(self):
        """Test that exceptions in websocket access are handled gracefully."""
        websocket = Mock()
        websocket.headers = {}
        websocket.query_params.get.side_effect = Exception("WebSocket access error")
        
        result = resolve_session_id(websocket=websocket, user_id="user_789")
        
        assert result == "user_789"

    def test_none_request_and_websocket(self):
        """Test behavior when both request and websocket are None."""
        result = resolve_session_id(request=None, websocket=None, user_id="user_789")
        
        assert result == "user_789"

    def test_empty_string_values(self):
        """Test that empty string values are treated as missing."""
        request = Mock(spec=Request)
        request.headers = {"X-Session-ID": ""}
        request.cookies = {"__session": "", "sid": ""}
        
        result = resolve_session_id(request=request, user_id="user_789")
        
        assert result == "user_789"


class TestGetCurrentSessionDevice:
    """Test the get_current_session_device function with centralized resolution."""

    def test_session_id_uses_centralized_resolution(self):
        """Test that session_id uses the centralized resolution function."""
        request = Mock(spec=Request)
        request.headers = {"X-Session-ID": "header_session_123", "X-Device-ID": "device_456"}
        request.cookies = {"__session": "sess_1234567890_abcdef12", "sid": "cookie_session_789", "did": "device_999"}
        
        result = get_current_session_device(request=request)
        
        # Should use __session cookie session ID (highest priority)
        assert result["session_id"] == "sess_1234567890_abcdef12"
        # Should use header device ID (highest priority)
        assert result["device_id"] == "device_456"

    def test_device_id_fallback_order(self):
        """Test device ID fallback order when X-Device-ID header is not present."""
        request = Mock(spec=Request)
        request.headers = {"X-Session-ID": "session_123"}
        request.cookies = {"did": "device_456"}
        
        result = get_current_session_device(request=request)
        
        assert result["session_id"] == "session_123"
        assert result["device_id"] == "device_456"

    def test_websocket_device_id(self):
        """Test device ID extraction from websocket query parameters."""
        websocket = Mock()
        websocket.query_params = {"sid": "session_123", "did": "device_456"}
        websocket.headers = {}
        
        result = get_current_session_device(websocket=websocket)
        
        assert result["session_id"] == "session_123"
        assert result["device_id"] == "device_456"

    def test_no_device_id(self):
        """Test behavior when no device ID is available."""
        request = Mock(spec=Request)
        request.headers = {"X-Session-ID": "session_123"}
        request.cookies = {}
        
        result = get_current_session_device(request=request)
        
        assert result["session_id"] == "session_123"
        assert result["device_id"] is None

    def test_exception_handling(self):
        """Test that exceptions are handled gracefully."""
        request = Mock(spec=Request)
        request.headers.get.side_effect = Exception("Access error")
        request.cookies = {}
        
        result = get_current_session_device(request=request)
        
        # Should still return a result even with exceptions
        assert "session_id" in result
        assert "device_id" in result


class TestIntegrationWithAuthEndpoints:
    """Test that the centralized session ID resolution works correctly in auth endpoints."""

    def test_logout_endpoint_uses_centralized_resolution(self, client):
        """Test that the logout endpoint uses centralized session ID resolution."""
        cookies = {"__session": "sess_1234567890_abcdef12", "sid": "cookie_session_123"}
        headers = {"X-Session-ID": "header_session_456"}
        
        # The logout endpoint should use __session cookie session ID (highest priority)
        # This test verifies the endpoint doesn't crash with the new centralized resolution
        response = client.post("/v1/auth/logout", cookies=cookies, headers=headers)
        
        # Should return 204 (success) regardless of token validity
        assert response.status_code == 204
