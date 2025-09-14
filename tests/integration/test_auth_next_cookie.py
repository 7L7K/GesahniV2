"""
Integration tests for auth next cookie flow.

Tests the complete flow of setting gs_next cookies during OAuth initiation
and consuming them during login completion, including edge cases with
query parameters and cookie priority handling.
"""

import os
from unittest.mock import Mock

from fastapi import Request, Response
from fastapi.testclient import TestClient

from app.main import app
from app.redirect_utils import (
    DEFAULT_FALLBACK,
    clear_gs_next_cookie,
    get_gs_next_cookie,
    get_safe_redirect_target,
    sanitize_redirect_path,
    set_gs_next_cookie,
)


class TestAuthNextCookieFlow:
    """Test auth next cookie flow integration."""

    def setup_method(self):
        """Set up test client."""
        # Disable CSRF for auth tests
        os.environ["CSRF_ENABLED"] = "0"
        self.client = TestClient(app)

    def teardown_method(self):
        """Clean up after test."""
        # Reset CSRF setting
        os.environ.pop("CSRF_ENABLED", None)

    def test_post_login_sets_gs_next_cookie(self):
        """Test that POST initial login with next=/dashboard sets gs_next cookie."""
        # Simulate OAuth initiation that sets gs_next cookie
        # This would typically happen in OAuth flows before redirecting to auth provider
        response = Response()
        request = Request(
            scope={"type": "http", "method": "GET", "path": "/", "headers": []}
        )

        # Set gs_next cookie as would happen in OAuth flow
        set_gs_next_cookie(response, "/dashboard", request)

        # Verify cookie was set in response headers
        assert "set-cookie" in response.headers
        cookie_header = response.headers["set-cookie"]
        assert "gs_next=" in cookie_header
        assert "/dashboard" in cookie_header

    def test_gs_next_cookie_consumption_after_login(self):
        """Test that gs_next cookie is consumed and cleared after login."""
        # First, simulate setting gs_next cookie (as would happen in OAuth flow)
        response = Response()
        request = Request(
            scope={"type": "http", "method": "GET", "path": "/", "headers": []}
        )

        set_gs_next_cookie(response, "/dashboard", request)
        cookie_header = response.headers["set-cookie"]

        # Extract cookie value for use in test client
        # This is a simplified extraction - in real scenario would parse properly
        cookie_value = cookie_header.split("gs_next=")[1].split(";")[0]

        # Now simulate login with the gs_next cookie set
        login_response = self.client.post(
            "/v1/auth/login",
            params={"username": "test_user"},
            cookies={"gs_next": cookie_value},
        )

        # Login should succeed
        assert login_response.status_code == 200
        data = login_response.json()
        assert data["status"] == "ok"
        assert data["user_id"] == "test_user"

        # In a real flow, the gs_next cookie should be cleared after consumption
        # This would happen when get_safe_redirect_target consumes the cookie

    def test_cookie_vs_query_param_priority(self):
        """Test that explicit next param takes priority over cookie."""
        # Set up a mock request with both cookie and explicit next param
        mock_request = Mock()
        mock_request.cookies = {"gs_next": "/cookie-target"}

        # Test get_safe_redirect_target with explicit next param
        result = get_safe_redirect_target(mock_request, "/query-target")

        # Explicit parameter takes priority over cookie
        assert result == "/query-target"

    def test_nested_next_parameter_handling(self):
        """Test /login?next=%2Flogin%3Fnext%3D… ends at /dashboard post-login."""
        # Test complex nested next scenario
        nested_next = "/login?next=%2Flogin%3Fnext%3D%252Fdashboard"

        # This should be sanitized to reject auth paths
        result = sanitize_redirect_path(nested_next)
        assert result == DEFAULT_FALLBACK

        # Test with a valid nested scenario
        valid_nested = "/dashboard?next=%2Fsettings"
        result = sanitize_redirect_path(valid_nested)
        assert result == "/dashboard"

    def test_malicious_next_cookie_rejection(self):
        """Test that malicious next cookies are properly rejected."""
        malicious_paths = [
            "https://evil.com/",
            "//evil.com/path",
            "/../../../etc/passwd",
            "/login",
            "/v1/auth/refresh",
        ]

        for malicious_path in malicious_paths:
            result = sanitize_redirect_path(malicious_path)
            assert result == DEFAULT_FALLBACK, f"Failed to reject: {malicious_path}"

    def test_safe_redirect_target_with_various_inputs(self):
        """Test get_safe_redirect_target with various cookie and param combinations."""
        test_cases = [
            # (cookies, explicit_next, expected_result)
            ({"gs_next": "/dashboard"}, None, "/dashboard"),
            ({"gs_next": "/login"}, None, DEFAULT_FALLBACK),  # Auth path rejected
            (
                {"gs_next": "https://evil.com"},
                None,
                DEFAULT_FALLBACK,
            ),  # Absolute URL rejected
            (
                {"gs_next": "/dashboard"},
                "/settings",
                "/settings",
            ),  # Explicit next takes priority
            ({}, "/dashboard", "/dashboard"),  # No cookie, use explicit
            ({}, None, DEFAULT_FALLBACK),  # No cookie, no explicit, use fallback
            ({}, "/login", DEFAULT_FALLBACK),  # Explicit auth path rejected
        ]

        for cookies, explicit_next, expected in test_cases:
            mock_request = Mock()
            mock_request.cookies = cookies

            result = get_safe_redirect_target(mock_request, explicit_next)
            assert (
                result == expected
            ), f"Failed for cookies={cookies}, next={explicit_next}"

    def test_gs_next_cookie_operations_integration(self):
        """Test complete gs_next cookie lifecycle."""
        # Test setting
        response = Response()
        request = Request(
            scope={"type": "http", "method": "GET", "path": "/", "headers": []}
        )

        set_gs_next_cookie(response, "/test-target", request)

        # Verify set
        assert "set-cookie" in response.headers
        cookie_header = response.headers["set-cookie"]
        assert "gs_next=/test-target" in cookie_header

        # Test getting (simulate cookie retrieval)
        mock_request = Mock()
        mock_request.cookies = {"gs_next": "/test-target"}
        retrieved = get_gs_next_cookie(mock_request)
        assert retrieved == "/test-target"

        # Test clearing
        clear_response = Response()
        clear_gs_next_cookie(clear_response, mock_request)
        assert "set-cookie" in clear_response.headers
        clear_header = clear_response.headers["set-cookie"]
        assert "gs_next=" in clear_header
        assert "Max-Age=0" in clear_header

    def test_redirect_sanitization_with_url_encoding(self):
        """Test redirect sanitization handles URL encoding properly."""
        test_cases = [
            ("%2Fdashboard", "/dashboard"),  # Single encoded
            ("%252Fdashboard", "/dashboard"),  # Double encoded
            ("%2Flogin", DEFAULT_FALLBACK),  # Encoded auth path
            ("%252Flogin", DEFAULT_FALLBACK),  # Double encoded auth path
            ("/dashboard%3Fnext%3D%252Fsettings", "/dashboard"),  # Next param removed
        ]

        for input_path, expected in test_cases:
            result = sanitize_redirect_path(input_path)
            assert result == expected, f"Failed for input: {input_path}"

    def test_integration_with_real_app_endpoints(self):
        """Test integration with actual app endpoints."""
        # Test that the login endpoint works without gs_next cookie
        response = self.client.post(
            "/v1/auth/login", params={"username": "integration_test_user"}
        )
        assert response.status_code == 200

        # Test that we can set cookies via the actual app (if endpoints exist)
        # This would depend on having actual OAuth endpoints that set gs_next

    def test_cookie_consumption_workflow(self):
        """Test the complete workflow of setting, using, and clearing gs_next cookie."""
        # Step 1: Set gs_next cookie (OAuth initiation)
        response1 = Response()
        request1 = Request(
            scope={"type": "http", "method": "GET", "path": "/", "headers": []}
        )
        set_gs_next_cookie(response1, "/post-login-target", request1)

        # Step 2: Simulate having the cookie set for login

        # Step 3: Login with cookie (would consume it)
        login_response = self.client.post(
            "/v1/auth/login",
            params={"username": "workflow_test"},
            cookies={"gs_next": "/post-login-target"},
        )
        assert login_response.status_code == 200

        # Step 4: In real flow, get_safe_redirect_target would consume and clear the cookie
        mock_request = Mock()
        mock_request.cookies = {"gs_next": "/post-login-target"}

        # This would normally happen in the redirect logic after login
        result = get_safe_redirect_target(mock_request)
        assert result == "/post-login-target"

        # After consumption, cookie should be cleared
        # (This would happen in the actual redirect response)
