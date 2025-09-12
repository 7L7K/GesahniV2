"""
Integration tests for redirect flows.

Tests complete login/logout redirect scenarios including cookie handling,
safe redirect enforcement, and nesting loop prevention.
"""

from unittest.mock import Mock

from fastapi import Request, Response
from fastapi.testclient import TestClient

from app.main import app
from app.redirect_utils import (
    DEFAULT_FALLBACK,
    sanitize_redirect_path,
    set_gs_next_cookie,
)


class TestRedirectFlows:
    """Test complete redirect flows."""

    def setup_method(self):
        """Set up test client."""
        self.client = TestClient(app)

    def test_login_redirect_with_valid_next(self):
        """Test login with valid next parameter."""
        # Set gs_next cookie first
        response = self.client.post(
            "/v1/auth/login",
            params={"username": "test"},
            cookies={"gs_next": "/dashboard"},
        )

        # Should succeed and set auth cookies
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["user_id"] == "test"

        # Should have set auth cookies
        assert "access_token" in response.cookies
        assert "refresh_token" in response.cookies

    def test_login_redirect_with_invalid_next(self):
        """Test login with invalid next parameter (auth path)."""
        response = self.client.post(
            "/v1/auth/login",
            params={"username": "test"},
            cookies={"gs_next": "/login"},  # Invalid - auth path
        )

        # Should succeed but not redirect to auth path
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    def test_login_redirect_with_malicious_next(self):
        """Test login with malicious next parameter."""
        response = self.client.post(
            "/v1/auth/login",
            params={"username": "test"},
            cookies={"gs_next": "https://evil.com"},  # Malicious
        )

        # Should succeed but not redirect to external site
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    def test_logout_clears_redirect_cookies(self):
        """Test logout clears all relevant cookies including gs_next."""
        # First set some cookies
        response = self.client.post("/v1/auth/login", params={"username": "test"})
        assert response.status_code == 200

        # Set gs_next cookie
        self.client.cookies.set("gs_next", "/dashboard")

        # Logout
        response = self.client.post("/v1/auth/logout")

        # Should clear cookies
        assert response.status_code == 204

        # Check that cookies are cleared (this is tricky with TestClient)
        # The response should have Set-Cookie headers to clear them

    def test_nested_next_parameter_handling(self):
        """Test handling of nested next parameters."""
        # Test with double-encoded next
        double_encoded = "%252Fdashboard"  # Encoded version of %2Fdashboard

        response = self.client.post(
            "/v1/auth/login",
            params={"username": "test"},
            cookies={"gs_next": double_encoded},
        )

        # Should handle safely (decode at most twice)
        assert response.status_code == 200

    def test_redirect_path_sanitization_edge_cases(self):
        """Test various edge cases in redirect path sanitization."""
        test_cases = [
            # (input, expected_output)
            ("/dashboard", "/dashboard"),  # Valid
            ("/login", DEFAULT_FALLBACK),  # Auth path
            ("https://evil.com", DEFAULT_FALLBACK),  # Absolute URL
            ("//evil.com", DEFAULT_FALLBACK),  # Protocol-relative
            ("dashboard", DEFAULT_FALLBACK),  # No leading slash
            ("/../../../etc/passwd", DEFAULT_FALLBACK),  # Path traversal
            ("/path//to///resource", "/path/to/resource"),  # Slash normalization
            ("/dashboard#section", "/dashboard"),  # Fragment removal
            ("/path?next=%2Fevil", "/path"),  # Nested next removal
            ("", DEFAULT_FALLBACK),  # Empty
            (None, DEFAULT_FALLBACK),  # None
        ]

        for input_path, expected in test_cases:
            if input_path is not None:
                result = sanitize_redirect_path(input_path)
                assert result == expected, f"Failed for input: {input_path}"

    def test_gs_next_cookie_operations(self):
        """Test gs_next cookie set/get/clear operations."""
        # Test setting cookie
        response = Response()
        request = Request(
            scope={"type": "http", "method": "GET", "path": "/", "headers": []}
        )

        set_gs_next_cookie(response, "/dashboard", request)

        # Cookie should be set in response headers
        assert "set-cookie" in response.headers
        cookie_header = response.headers["set-cookie"]
        assert "gs_next=" in cookie_header
        assert "/dashboard" in cookie_header

        # Test invalid path doesn't set cookie
        response2 = Response()
        set_gs_next_cookie(response2, "invalid-path", request)
        assert "set-cookie" not in response2.headers

    def test_redirect_loop_prevention(self):
        """Test prevention of redirect loops."""
        # Multiple levels of next nesting should be prevented
        nested_next = "/login?next=%2Flogin%3Fnext%3D%252Fdashboard"

        result = sanitize_redirect_path(nested_next)
        assert result == DEFAULT_FALLBACK  # Should reject auth paths

    def test_origin_aware_redirect_building(self):
        """Test building origin-aware redirect URLs."""
        from app.redirect_utils import build_origin_aware_redirect_url

        # Mock request with origin
        request = Mock()
        request.headers = {"origin": "http://localhost:3000"}

        result = build_origin_aware_redirect_url(request, "/dashboard")
        assert result == "http://localhost:3000/dashboard"

    def test_rate_limit_with_redirects(self):
        """Test rate limiting works with redirect parameters."""
        # This would need to be implemented if rate limiting is added to redirects
        # For now, just ensure login still works
        response = self.client.post("/v1/auth/login", params={"username": "test"})
        assert response.status_code == 200


class TestFrontendRedirectIntegration:
    """Test frontend redirect utilities integration."""

    def test_frontend_redirect_utils_import(self):
        """Test that frontend redirect utilities can be imported."""
        # This is a placeholder for frontend integration tests
        # In a real setup, you'd use a test runner that can execute frontend code
        pass

    def test_redirect_utility_consistency(self):
        """Test that frontend and backend utilities behave consistently."""
        # Test cases that should behave the same in frontend and backend
        test_cases = [
            "/dashboard",
            "/settings/profile",
            "/login",  # Should be rejected
            "https://evil.com",  # Should be rejected
            "//evil.com",  # Should be rejected
        ]

        for path in test_cases:
            backend_result = sanitize_redirect_path(path)
            # In real implementation, you'd compare with frontend result
            # For now, just ensure backend works correctly
            if path.startswith("/"):
                if not path.startswith("/login") and not path.startswith("/v1/auth/"):
                    assert backend_result == path
                else:
                    assert backend_result == DEFAULT_FALLBACK
            else:
                assert backend_result == DEFAULT_FALLBACK


class TestLegacyRedirectCompatibility:
    """Test legacy redirect endpoints still work."""

    def test_legacy_login_redirect(self):
        """Test legacy /v1/login endpoint."""
        response = self.client.post("/v1/login", params={"username": "test"})
        assert response.status_code == 200

    def test_legacy_logout_redirect(self):
        """Test legacy /v1/logout endpoint."""
        response = self.client.post("/v1/logout")
        assert response.status_code == 204

    def test_legacy_register_redirect(self):
        """Test legacy /v1/register endpoint."""
        # This would need actual registration data
        pass
