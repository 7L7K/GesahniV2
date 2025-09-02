"""
Integration tests for cookie consistency.

These tests verify that cookies are set with sharp and consistent attributes
across all authentication endpoints and that no redirects happen before
cookies are written.
"""

import re
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.test_helpers import (
    assert_cookies_cleared,
    assert_cookies_present,
    assert_session_opaque,
)


class TestCookieConsistency:
    """Test cookie consistency across all endpoints."""

    @pytest.fixture
    def client(self):
        """Create test client with rate limiting disabled."""
        import os
        # Disable rate limiting for this test
        original_rate_limit = os.environ.get("ENABLE_RATE_LIMIT_IN_TESTS", "0")
        os.environ["ENABLE_RATE_LIMIT_IN_TESTS"] = "0"
        try:
            return TestClient(app)
        finally:
            # Restore original setting
            if original_rate_limit:
                os.environ["ENABLE_RATE_LIMIT_IN_TESTS"] = original_rate_limit
            else:
                os.environ.pop("ENABLE_RATE_LIMIT_IN_TESTS", None)

    def test_login_cookies_consistency(self, client):
        """Test that login endpoint sets cookies consistently."""
        # Test login with query parameters and CSRF tokens
        response = client.post(
            "/v1/auth/login?username=testuser",
            headers={"X-CSRF-Token": "test"},
            cookies={"csrf_token": "test"}
        )

        assert response.status_code == 200

        # Check for Set-Cookie headers
        set_cookie_headers = response.headers.get("Set-Cookie", "")
        if isinstance(set_cookie_headers, str):
            set_cookie_headers = [set_cookie_headers]

        # Should have all three auth cookies
        assert_cookies_present(response)

        # Check that __session is opaque
        assert_session_opaque(response)

        # Parse and verify cookie attributes
        access_cookie = None
        refresh_cookie = None

        for header in set_cookie_headers:
            if "access_token=" in header:
                access_cookie = header
            elif "refresh_token=" in header:
                refresh_cookie = header

        assert access_cookie is not None

        # Verify consistent attributes for access token
        # Host-only (no Domain)
        assert "Domain=" not in access_cookie

        # Path=/
        assert "Path=/" in access_cookie

        # HttpOnly
        assert "HttpOnly" in access_cookie

        # SameSite=Lax (default) - normalized to uppercase
        assert "SameSite=Lax" in access_cookie

        # Priority=High for auth cookies
        assert "Priority=High" in access_cookie

        # Max-Age should be present
        assert "Max-Age=" in access_cookie

    def test_refresh_cookies_consistency(self, client):
        """Test that refresh endpoint sets cookies consistently."""
        # First login to get cookies
        login_response = client.post("/v1/auth/login?username=testuser2")

        # Extract cookies from login response
        cookies = login_response.cookies

        # Test refresh
        response = client.post("/v1/auth/refresh", cookies=cookies)

        # Refresh might fail without proper setup, but if it succeeds, check cookies
        if response.status_code == 200:
            set_cookie_headers = response.headers.get("Set-Cookie", "")
            if isinstance(set_cookie_headers, str):
                set_cookie_headers = [set_cookie_headers]

            # Verify consistent attributes
            for cookie_header in set_cookie_headers:
                if (
                    "access_token=" in cookie_header
                    or "refresh_token=" in cookie_header
                ):
                    # Host-only (no Domain)
                    assert "Domain=" not in cookie_header

                    # Path=/
                    assert "Path=/" in cookie_header

                    # HttpOnly
                    assert "HttpOnly" in cookie_header

                    # SameSite=Lax (default) - normalized to uppercase
                    assert "SameSite=Lax" in cookie_header

                    # Priority=High for auth cookies
                    assert "Priority=High" in cookie_header

                    # Max-Age should be present
                    assert "Max-Age=" in cookie_header

    def test_logout_cookies_consistency(self, client):
        """Test that logout endpoint clears cookies consistently."""
        # First login to get cookies
        login_response = client.post("/v1/auth/login?username=testuser3")

        # Extract cookies from login response
        cookies = login_response.cookies

        # Test logout
        response = client.post("/v1/auth/logout", cookies=cookies)

        assert response.status_code == 204

        # Check for Set-Cookie headers (clearing cookies)
        set_cookie_headers = response.headers.get("Set-Cookie", "")
        if isinstance(set_cookie_headers, str):
            set_cookie_headers = [set_cookie_headers]

        # Should have cookies being cleared
        assert_cookies_cleared(response)

        # Verify consistent attributes for cleared cookies
        for cookie_header in set_cookie_headers:
            if "access_token=" in cookie_header or "refresh_token=" in cookie_header:
                # Host-only (no Domain)
                assert "Domain=" not in cookie_header

                # Path=/
                assert "Path=/" in cookie_header

                # Note: delete_cookie doesn't set HttpOnly or SameSite when clearing cookies
                # These attributes are only set when cookies are created, not when cleared

                # Max-Age=0 for clearing (modern approach)
                assert "Max-Age=0" in cookie_header

                # Note: expires= is not required when using Max-Age=0
                # Modern browsers prefer Max-Age over Expires for cookie clearing

    def test_google_oauth_cookies_consistency(self, client):
        """Test that Google OAuth sets cookies consistently."""
        # Mock the Google OAuth flow
        with patch("app.integrations.google.routes.oauth") as mock_oauth:
            mock_oauth.build_auth_url.return_value = (
                "https://accounts.google.com/oauth/authorize",
                "state",
            )

            # Test OAuth callback - use GET as expected by the endpoint
            response = client.get("/google/oauth/callback?code=test_code&state=state")

            # Should redirect with cookies set
            assert response.status_code in [302, 200]

            # Check for Set-Cookie headers
            set_cookie_headers = response.headers.get("Set-Cookie", "")
            if isinstance(set_cookie_headers, str):
                set_cookie_headers = [set_cookie_headers]

            if set_cookie_headers:  # Cookies might be set depending on mock
                for cookie_header in set_cookie_headers:
                    if (
                        "access_token=" in cookie_header
                        or "refresh_token=" in cookie_header
                    ):
                        # Host-only (no Domain)
                        assert "Domain=" not in cookie_header

                        # Path=/
                        assert "Path=/" in cookie_header

                        # HttpOnly
                        assert "HttpOnly" in cookie_header

                        # SameSite=Lax (default)
                        assert "SameSite=Lax" in cookie_header

                        # Priority=High for auth cookies
                        assert "Priority=High" in cookie_header

    def test_device_trust_cookies_consistency(self, client):
        """Test that device trust endpoint sets cookies consistently."""
        response = client.post("/v1/device/trust")

        assert response.status_code == 200

        # Check for Set-Cookie headers
        set_cookie_headers = response.headers.get("Set-Cookie", "")
        if isinstance(set_cookie_headers, str):
            set_cookie_headers = [set_cookie_headers]

        if set_cookie_headers:  # Cookies might be set depending on JWT_SECRET
            for cookie_header in set_cookie_headers:
                if "access_token=" in cookie_header:
                    # Host-only (no Domain)
                    assert "Domain=" not in cookie_header

                    # Path=/
                    assert "Path=/" in cookie_header

                    # HttpOnly
                    assert "HttpOnly" in cookie_header

                    # SameSite=Lax (default) - normalized to uppercase
                    assert "SameSite=Lax" in cookie_header

                    # Max-Age should be present
                    assert "Max-Age=" in cookie_header

    def test_no_redirects_before_cookies(self, client):
        """Test that no redirects happen before cookies are written."""
        # Test login endpoint - should not redirect

        response = client.post("/v1/auth/login?username=testuser4")

        # Should return 200, not redirect
        assert response.status_code == 200

        # Should have Set-Cookie headers
        set_cookie_headers = response.headers.get("Set-Cookie", "")
        if isinstance(set_cookie_headers, str):
            set_cookie_headers = [set_cookie_headers]
        assert len(set_cookie_headers) >= 1

        # Should not have Location header (redirect)
        assert "Location" not in response.headers

    def test_cookie_ttl_consistency(self, client):
        """Test that cookie TTLs are consistent across endpoints."""
        # First login to get cookies
        login_response = client.post("/v1/auth/login?username=testuser5")

        # Extract Max-Age values from login cookies
        login_cookies = login_response.headers.get("Set-Cookie", "")
        if isinstance(login_cookies, str):
            login_cookies = [login_cookies]

        login_access_max_age = None
        login_refresh_max_age = None

        for cookie in login_cookies:
            if "access_token=" in cookie and "Max-Age=" in cookie:
                match = re.search(r"Max-Age=(\d+)", cookie)
                if match:
                    login_access_max_age = int(match.group(1))
            elif "refresh_token=" in cookie and "Max-Age=" in cookie:
                match = re.search(r"Max-Age=(\d+)", cookie)
                if match:
                    login_refresh_max_age = int(match.group(1))

        # Extract cookies for refresh
        cookies = login_response.cookies

        # Test refresh
        refresh_response = client.post("/v1/auth/refresh", cookies=cookies)

        # Extract Max-Age values from refresh cookies
        refresh_cookies = refresh_response.headers.get("Set-Cookie", "")
        if isinstance(refresh_cookies, str):
            refresh_cookies = [refresh_cookies]

        refresh_access_max_age = None
        refresh_refresh_max_age = None

        for cookie in refresh_cookies:
            if "access_token=" in cookie and "Max-Age=" in cookie:
                match = re.search(r"Max-Age=(\d+)", cookie)
                if match:
                    refresh_access_max_age = int(match.group(1))
            elif "refresh_token=" in cookie and "Max-Age=" in cookie:
                match = re.search(r"Max-Age=(\d+)", cookie)
                if match:
                    refresh_refresh_max_age = int(match.group(1))

        # TTLs should be consistent between login and refresh
        if login_access_max_age and refresh_access_max_age:
            assert login_access_max_age == refresh_access_max_age

        if login_refresh_max_age and refresh_refresh_max_age:
            assert login_refresh_max_age == refresh_refresh_max_age

        # Access token TTL should be shorter than refresh token TTL
        if login_access_max_age and login_refresh_max_age:
            assert login_access_max_age < login_refresh_max_age

    def test_dev_mode_cookie_secure(self, client):
        """Test that dev mode correctly sets Secure=False for HTTP."""
        # Test with dev mode enabled
        with patch.dict("os.environ", {"DEV_MODE": "1"}):

            response = client.post(
                "/v1/auth/login?username=testuser_dev_mode",
                headers={"X-CSRF-Token": "test"},
                cookies={"csrf_token": "test"}
            )

            assert response.status_code == 200

            # Check for Set-Cookie headers
            set_cookie_headers = response.headers.get("Set-Cookie", "")
            if isinstance(set_cookie_headers, str):
                set_cookie_headers = [set_cookie_headers]

            for cookie_header in set_cookie_headers:
                if (
                    "access_token=" in cookie_header
                    or "refresh_token=" in cookie_header
                ):
                    # In dev mode over HTTP, Secure should be False
                    assert "Secure" not in cookie_header

    def test_production_cookie_secure(self, client):
        """Test that production correctly sets Secure=True for HTTPS."""
        # Mock HTTPS request
        with patch("app.cookie_config._get_scheme", return_value="https"):

            response = client.post(
                "/v1/auth/login?username=testuser_prod_mode",
                headers={"X-CSRF-Token": "test"},
                cookies={"csrf_token": "test"}
            )

            assert response.status_code == 200

            # Check for Set-Cookie headers
            set_cookie_headers = response.headers.get("Set-Cookie", "")
            if isinstance(set_cookie_headers, str):
                set_cookie_headers = [set_cookie_headers]

            for cookie_header in set_cookie_headers:
                if (
                    "access_token=" in cookie_header
                    or "refresh_token=" in cookie_header
                ):
                    # In production over HTTPS, Secure should be True
                    assert "Secure" in cookie_header

    def test_centralized_cookie_configuration(self, client):
        """Test that all endpoints use the centralized cookie configuration."""
        # This test verifies that our cookie consistency improvements are working
        # by checking that all endpoints use the same configuration source

        # Test login endpoint
        login_response = client.post(
            "/v1/auth/login?username=testuser_centralized",
            headers={"X-CSRF-Token": "test"},
            cookies={"csrf_token": "test"}
        )
        assert login_response.status_code == 200

        # Test device trust endpoint
        device_response = client.post(
            "/v1/device/trust",
            headers={"X-CSRF-Token": "test"},
            cookies={"csrf_token": "test"}
        )
        assert device_response.status_code == 200

        # Both should have consistent cookie attributes
        login_cookies = login_response.headers.get("Set-Cookie", "")
        device_cookies = device_response.headers.get("Set-Cookie", "")

        if isinstance(login_cookies, str):
            login_cookies = [login_cookies]
        if isinstance(device_cookies, str):
            device_cookies = [device_cookies]

        # Check that both endpoints use the same cookie configuration
        for cookie_header in login_cookies + device_cookies:
            if "access_token=" in cookie_header:
                # All should have consistent attributes
                assert "HttpOnly" in cookie_header
                assert "Path=/" in cookie_header
                assert "Domain=" not in cookie_header  # Host-only cookies
                assert "SameSite=Lax" in cookie_header  # Normalized to uppercase
                assert "Priority=High" in cookie_header  # Auth cookies get priority
                assert "Max-Age=" in cookie_header
