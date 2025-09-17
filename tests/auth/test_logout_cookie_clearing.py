"""
Test logout clears access, refresh, __session, device_id—assert via /debug/cookies.

This test file verifies that the logout endpoint properly clears all authentication
cookies and that the /debug/cookies endpoint can be used to verify the clearing.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client():
    """Create test client with authenticated user."""
    app = create_app()
    return TestClient(app)


class TestLogoutCookieClearing:
    """Test that logout properly clears all authentication cookies."""

    def test_debug_cookies_endpoint_returns_cookie_status(self, client):
        """Test that /debug/cookies endpoint properly reports cookie presence."""

        # Set some test cookies
        client.cookies.set("test_cookie", "present")
        client.cookies.set("GSNH_AT", "token_value")
        client.cookies.set("GSNH_RT", "refresh_value")
        client.cookies.set("__session", "session_value")
        client.cookies.set("device_id", "device_value")

        response = client.get("/v1/auth/debug/cookies")
        assert response.status_code == 200

        data = response.json()
        assert "cookies" in data

        cookies = data["cookies"]

        # Should report presence without exposing values
        assert "test_cookie" in cookies
        assert "GSNH_AT" in cookies
        assert "GSNH_RT" in cookies
        assert "__session" in cookies
        assert "device_id" in cookies

        # Values should be "present" or empty string, not actual values
        assert cookies["test_cookie"] in ["present", ""]
        assert cookies["GSNH_AT"] in ["present", ""]
        assert cookies["GSNH_RT"] in ["present", ""]

    def test_logout_clears_access_token_cookie(self, client):
        """Test that logout clears the access token cookie."""

        # Login to set cookies
        login_response = client.post("/v1/auth/login", json={"username": "test_user"})
        assert login_response.status_code == 200

        # Verify access cookie is present
        debug_response = client.get("/debug/cookies")
        assert debug_response.status_code == 200
        cookies_before = debug_response.json()["cookies"]

        # Access token cookie should be present (may be named differently)
        access_cookie_present = any(
            cookie_name in cookies_before and cookies_before[cookie_name] == "present"
            for cookie_name in ["GSNH_AT", "access_token", "access"]
        )
        if not access_cookie_present:
            pytest.skip("Access token cookie not set during login")

        # Perform logout
        logout_response = client.post("/v1/auth/logout")
        assert logout_response.status_code == 204

        # Verify access cookie is cleared
        debug_response = client.get("/debug/cookies")
        assert debug_response.status_code == 200
        cookies_after = debug_response.json()["cookies"]

        # Access token cookie should be absent or empty
        access_cookie_cleared = all(
            cookies_after.get(cookie_name, "") != "present"
            for cookie_name in ["GSNH_AT", "access_token", "access"]
        )
        assert (
            access_cookie_cleared
        ), f"Access token cookie not cleared: {cookies_after}"

    def test_logout_clears_refresh_token_cookie(self, client):
        """Test that logout clears the refresh token cookie."""

        # Login to set cookies
        login_response = client.post("/v1/auth/login", json={"username": "test_user"})
        assert login_response.status_code == 200

        # Verify refresh cookie is present
        debug_response = client.get("/debug/cookies")
        assert debug_response.status_code == 200
        cookies_before = debug_response.json()["cookies"]

        # Refresh token cookie should be present
        refresh_cookie_present = any(
            cookie_name in cookies_before and cookies_before[cookie_name] == "present"
            for cookie_name in ["GSNH_RT", "refresh_token", "refresh"]
        )
        if not refresh_cookie_present:
            pytest.skip("Refresh token cookie not set during login")

        # Perform logout
        logout_response = client.post("/v1/auth/logout")
        assert logout_response.status_code == 204

        # Verify refresh cookie is cleared
        debug_response = client.get("/debug/cookies")
        assert debug_response.status_code == 200
        cookies_after = debug_response.json()["cookies"]

        # Refresh token cookie should be absent or empty
        refresh_cookie_cleared = all(
            cookies_after.get(cookie_name, "") != "present"
            for cookie_name in ["GSNH_RT", "refresh_token", "refresh"]
        )
        assert (
            refresh_cookie_cleared
        ), f"Refresh token cookie not cleared: {cookies_after}"

    def test_logout_clears_session_cookie(self, client):
        """Test that logout clears the session cookie."""

        # Login to set cookies
        login_response = client.post("/v1/auth/login", json={"username": "test_user"})
        assert login_response.status_code == 200

        # Verify session cookie is present
        debug_response = client.get("/debug/cookies")
        assert debug_response.status_code == 200
        cookies_before = debug_response.json()["cookies"]

        # Session cookie should be present
        session_cookie_present = any(
            cookie_name in cookies_before and cookies_before[cookie_name] == "present"
            for cookie_name in ["__session", "session", "session_id"]
        )
        if not session_cookie_present:
            pytest.skip("Session cookie not set during login")

        # Perform logout
        logout_response = client.post("/v1/auth/logout")
        assert logout_response.status_code == 204

        # Verify session cookie is cleared
        debug_response = client.get("/debug/cookies")
        assert debug_response.status_code == 200
        cookies_after = debug_response.json()["cookies"]

        # Session cookie should be absent or empty
        session_cookie_cleared = all(
            cookies_after.get(cookie_name, "") != "present"
            for cookie_name in ["__session", "session", "session_id"]
        )
        assert session_cookie_cleared, f"Session cookie not cleared: {cookies_after}"

    def test_logout_clears_device_id_cookie(self, client):
        """Test that logout clears the device_id cookie."""

        # Login to set cookies
        login_response = client.post("/v1/auth/login", json={"username": "test_user"})
        assert login_response.status_code == 200

        # Verify device_id cookie is present
        debug_response = client.get("/debug/cookies")
        assert debug_response.status_code == 200
        cookies_before = debug_response.json()["cookies"]

        # Device ID cookie should be present
        device_cookie_present = any(
            cookie_name in cookies_before and cookies_before[cookie_name] == "present"
            for cookie_name in ["device_id", "did", "device"]
        )
        if not device_cookie_present:
            pytest.skip("Device ID cookie not set during login")

        # Perform logout
        logout_response = client.post("/v1/auth/logout")
        assert logout_response.status_code == 204

        # Verify device_id cookie is cleared
        debug_response = client.get("/debug/cookies")
        assert debug_response.status_code == 200
        cookies_after = debug_response.json()["cookies"]

        # Device ID cookie should be absent or empty
        device_cookie_cleared = all(
            cookies_after.get(cookie_name, "") != "present"
            for cookie_name in ["device_id", "did", "device"]
        )
        assert device_cookie_cleared, f"Device ID cookie not cleared: {cookies_after}"

    def test_logout_clears_all_auth_cookies_comprehensive(self, client):
        """Test that logout clears all authentication-related cookies."""

        # Login to set cookies
        login_response = client.post("/v1/auth/login", json={"username": "test_user"})
        assert login_response.status_code == 200

        # Get initial cookie state
        debug_response = client.get("/debug/cookies")
        assert debug_response.status_code == 200
        cookies_before = debug_response.json()["cookies"]

        # Identify which auth cookies are present
        auth_cookie_names = [
            "GSNH_AT",
            "GSNH_RT",
            "__session",
            "device_id",
            "did",
            "access_token",
            "refresh_token",
        ]
        present_auth_cookies = [
            name
            for name in auth_cookie_names
            if name in cookies_before and cookies_before[name] == "present"
        ]

        if not present_auth_cookies:
            pytest.skip("No auth cookies present after login")

        # Perform logout
        logout_response = client.post("/v1/auth/logout")
        assert logout_response.status_code == 204

        # Verify all auth cookies are cleared
        debug_response = client.get("/debug/cookies")
        assert debug_response.status_code == 200
        cookies_after = debug_response.json()["cookies"]

        # All previously present auth cookies should be cleared
        for cookie_name in present_auth_cookies:
            assert (
                cookies_after.get(cookie_name, "") != "present"
            ), f"Cookie {cookie_name} not cleared after logout"

    def test_logout_all_clears_cookies(self, client):
        """Test that logout_all endpoint also clears cookies."""

        # Login to set cookies
        login_response = client.post("/v1/auth/login", json={"username": "test_user"})
        assert login_response.status_code == 200

        # Verify some cookies are set
        debug_response = client.get("/debug/cookies")
        assert debug_response.status_code == 200
        cookies_before = debug_response.json()["cookies"]

        # Perform logout_all
        logout_response = client.post("/v1/auth/logout_all")
        assert logout_response.status_code == 204

        # Verify cookies are cleared
        debug_response = client.get("/debug/cookies")
        assert debug_response.status_code == 200
        cookies_after = debug_response.json()["cookies"]

        # Auth cookies should be cleared
        auth_cookies = ["GSNH_AT", "GSNH_RT", "__session", "device_id", "did"]
        for cookie_name in auth_cookies:
            assert (
                cookies_after.get(cookie_name, "") != "present"
            ), f"Cookie {cookie_name} not cleared after logout_all"

    def test_logout_cookies_cleared_via_set_cookie_headers(self, client):
        """Test that logout sets proper Set-Cookie headers to clear cookies."""

        # Login to set cookies
        login_response = client.post("/v1/auth/login", json={"username": "test_user"})
        assert login_response.status_code == 200

        # Perform logout and check Set-Cookie headers
        logout_response = client.post("/v1/auth/logout")

        assert logout_response.status_code == 204

        # Check Set-Cookie headers in logout response
        set_cookie_headers = logout_response.headers.get_list("set-cookie")

        # Should have Set-Cookie headers that clear auth cookies
        cleared_cookies = []
        for header in set_cookie_headers:
            # Parse cookie name and check if it's being cleared (max-age=0 or expired date)
            if "=" in header:
                cookie_name = header.split("=", 1)[0].strip()
                if cookie_name in [
                    "GSNH_AT",
                    "GSNH_RT",
                    "__session",
                    "device_id",
                    "did",
                ]:
                    # Check if it's being cleared (max-age=0 or past date)
                    if "max-age=0" in header or "expires=" in header:
                        cleared_cookies.append(cookie_name)

        # Should clear the main auth cookies
        expected_cleared = ["GSNH_AT", "GSNH_RT", "__session"]
        for cookie_name in expected_cleared:
            assert (
                cookie_name in cleared_cookies
            ), f"Cookie {cookie_name} not properly cleared in Set-Cookie header"

    def test_logout_cookies_verified_by_subsequent_request(self, client):
        """Test that cookies remain cleared after logout by making subsequent requests."""

        # Login
        login_response = client.post("/v1/auth/login", json={"username": "test_user"})
        assert login_response.status_code == 200

        # Verify authenticated
        whoami_response = client.get("/v1/whoami")
        assert whoami_response.status_code == 200
        whoami_data = whoami_response.json()
        assert whoami_data.get("is_authenticated") is True

        # Logout
        logout_response = client.post("/v1/auth/logout")
        assert logout_response.status_code == 204

        # Verify no longer authenticated
        whoami_response = client.get("/v1/whoami")
        assert whoami_response.status_code == 401

        # Verify cookies still cleared
        debug_response = client.get("/debug/cookies")
        assert debug_response.status_code == 200
        cookies_after = debug_response.json()["cookies"]

        # Auth cookies should remain cleared
        auth_cookies = ["GSNH_AT", "GSNH_RT", "__session", "device_id", "did"]
        for cookie_name in auth_cookies:
            assert (
                cookies_after.get(cookie_name, "") != "present"
            ), f"Cookie {cookie_name} reappeared after logout"

    def test_logout_preserves_non_auth_cookies(self, client):
        """Test that logout only clears auth cookies, not other cookies."""

        # Set a non-auth cookie
        client.cookies.set("user_preference", "dark_mode")
        client.cookies.set("analytics_id", "12345")

        # Login to set auth cookies
        login_response = client.post("/v1/auth/login", json={"username": "test_user"})
        assert login_response.status_code == 200

        # Logout
        logout_response = client.post("/v1/auth/logout")
        assert logout_response.status_code == 204

        # Check cookies after logout
        debug_response = client.get("/debug/cookies")
        assert debug_response.status_code == 200
        cookies_after = debug_response.json()["cookies"]

        # Non-auth cookies should be preserved
        assert (
            cookies_after.get("user_preference", "") == "present"
        ), "Non-auth cookie was cleared"
        assert (
            cookies_after.get("analytics_id", "") == "present"
        ), "Analytics cookie was cleared"

        # Auth cookies should be cleared
        auth_cookies = ["GSNH_AT", "GSNH_RT", "__session", "device_id", "did"]
        for cookie_name in auth_cookies:
            assert (
                cookies_after.get(cookie_name, "") != "present"
            ), f"Auth cookie {cookie_name} not cleared"
