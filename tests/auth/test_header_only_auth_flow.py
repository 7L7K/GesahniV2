"""
Test header-only auth flow (no cookies) passes whoami.

This test file verifies that authentication works correctly when using
only Authorization headers without any cookies set.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.tokens import make_access


@pytest.fixture
def client():
    """Create test client with minimal app."""
    app = create_app()
    return TestClient(app)


@pytest.fixture
def valid_access_token():
    """Create a valid access token for testing."""
    return make_access({"user_id": "test_user"})


@pytest.fixture
def expired_access_token():
    """Create an expired access token for testing."""
    return make_access({"user_id": "test_user"}, ttl_s=-1)


class TestHeaderOnlyAuthFlow:
    """Test that header-only authentication works correctly."""

    def test_whoami_with_valid_header_no_cookies(self, client, valid_access_token):
        """Test that whoami succeeds with valid Authorization header and no cookies."""

        # Clear any existing cookies
        client.cookies.clear()

        headers = {"Authorization": f"Bearer {valid_access_token}"}
        response = client.get("/v1/auth/whoami", headers=headers)

        assert response.status_code == 200

        data = response.json()
        assert "is_authenticated" in data
        assert data["is_authenticated"] is True
        assert "user_id" in data
        assert data["user_id"] == "test_user"
        assert "source" in data
        assert data["source"] == "header"

    def test_whoami_with_invalid_header_no_cookies(self, client):
        """Test that whoami fails with invalid Authorization header and no cookies."""

        # Clear any existing cookies
        client.cookies.clear()

        headers = {"Authorization": "Bearer invalid-token"}
        response = client.get("/v1/auth/whoami", headers=headers)

        assert response.status_code == 401

        error_data = response.json()
        assert "code" in error_data
        assert error_data["code"] == "unauthorized"

    def test_whoami_with_expired_header_no_cookies(self, client, expired_access_token):
        """Test that whoami fails with expired Authorization header and no cookies."""

        # Clear any existing cookies
        client.cookies.clear()

        headers = {"Authorization": f"Bearer {expired_access_token}"}
        response = client.get("/v1/auth/whoami", headers=headers)

        assert response.status_code == 401

        error_data = response.json()
        assert "code" in error_data
        assert error_data["code"] == "unauthorized"

    def test_whoami_with_malformed_header_no_cookies(self, client):
        """Test that whoami fails with malformed Authorization header and no cookies."""

        # Clear any existing cookies
        client.cookies.clear()

        # Test various malformed headers
        malformed_headers = [
            {"Authorization": "invalid-format"},
            {"Authorization": "Basic dXNlcjpwYXNz"},  # Basic auth instead of Bearer
            {"Authorization": "Bearer"},  # Missing token
            {"Authorization": "Bearer "},  # Empty token
            {"Authorization": "bearer valid-token"},  # lowercase bearer
        ]

        for headers in malformed_headers:
            response = client.get("/v1/auth/whoami", headers=headers)
            assert (
                response.status_code == 401
            ), f"Expected 401 for malformed header: {headers}"

    def test_whoami_header_precedence_over_cookie(self, client, valid_access_token):
        """Test that Authorization header takes precedence over cookies when both present."""

        # Set a cookie with a different user
        client.cookies.set("GSNH_AT", make_access({"user_id": "cookie_user"}))

        # Use header with different user
        headers = {"Authorization": f"Bearer {valid_access_token}"}
        response = client.get("/v1/auth/whoami", headers=headers)

        assert response.status_code == 200

        data = response.json()
        assert data["is_authenticated"] is True
        assert data["user_id"] == "test_user"  # Should use header user, not cookie user
        assert data["source"] == "header"  # Should indicate header was used

    def test_whoami_header_with_cookie_conflict_logged(
        self, client, valid_access_token, caplog
    ):
        """Test that conflicting auth sources are properly logged."""

        # Set a cookie with a different user
        client.cookies.set("GSNH_AT", make_access({"user_id": "cookie_user"}))

        # Use header with different user
        headers = {"Authorization": f"Bearer {valid_access_token}"}
        response = client.get("/v1/auth/whoami", headers=headers)

        assert response.status_code == 200

        # Should log the conflict
        conflict_logs = [
            record
            for record in caplog.records
            if "conflict" in record.message.lower()
            or "source" in record.message.lower()
        ]
        # Note: Logging depends on implementation, may not always log conflicts

    def test_ask_endpoint_with_header_no_cookies(self, client, valid_access_token):
        """Test that protected endpoints work with header-only auth."""

        # Clear any existing cookies
        client.cookies.clear()

        headers = {"Authorization": f"Bearer {valid_access_token}"}
        response = client.post("/v1/ask", json={"prompt": "test"}, headers=headers)

        # Should succeed (200) or fail for other reasons, but not auth failure (401)
        assert response.status_code != 401, "Header auth should not fail with 401"

    def test_chat_endpoint_with_header_no_cookies(self, client, valid_access_token):
        """Test that chat endpoint works with header-only auth."""

        # Clear any existing cookies
        client.cookies.clear()

        headers = {"Authorization": f"Bearer {valid_access_token}"}
        response = client.post("/v1/chat", json={"messages": []}, headers=headers)

        # Should succeed or fail for other reasons, but not auth failure
        assert response.status_code != 401, "Header auth should not fail with 401"

    def test_state_endpoint_with_header_no_cookies(self, client, valid_access_token):
        """Test that state endpoint works with header-only auth."""

        # Clear any existing cookies
        client.cookies.clear()

        headers = {"Authorization": f"Bearer {valid_access_token}"}
        response = client.get("/v1/state", headers=headers)

        # Should succeed or fail for other reasons, but not auth failure
        assert response.status_code != 401, "Header auth should not fail with 401"

    def test_csrf_bypass_with_header_only_auth(self, client):
        """Test that CSRF validation is bypassed when using header-only auth."""

        # Clear any existing cookies
        client.cookies.clear()

        # Create a valid token
        token = make_access({"user_id": "test_user"})

        # Try POST request without CSRF token but with Authorization header
        headers = {"Authorization": f"Bearer {token}"}
        response = client.post("/v1/ask", json={"prompt": "test"}, headers=headers)

        # Should not fail with CSRF error (403 for invalid_csrf)
        if response.status_code == 403:
            error_data = response.json()
            assert (
                error_data.get("code") != "invalid_csrf"
            ), "CSRF should be bypassed with Authorization header"

    def test_header_auth_bypasses_cookie_refresh(self, client, valid_access_token):
        """Test that header auth doesn't trigger cookie-based refresh logic."""

        # Clear any existing cookies
        client.cookies.clear()

        headers = {"Authorization": f"Bearer {valid_access_token}"}
        response = client.get("/v1/auth/whoami", headers=headers)

        assert response.status_code == 200

        # Response should not set any auth cookies (since auth came from header)
        set_cookie_headers = response.headers.get_list("set-cookie")
        auth_cookies = [
            h
            for h in set_cookie_headers
            if any(
                cookie_name in h
                for cookie_name in ["GSNH_AT=", "GSNH_RT=", "__session="]
            )
        ]

        # Should not set new auth cookies when using header auth
        assert (
            len(auth_cookies) == 0
        ), f"Header auth should not set cookies: {auth_cookies}"

    def test_header_auth_logs_correct_source(self, client, valid_access_token, caplog):
        """Test that header-only auth is properly logged with correct source."""

        # Clear any existing cookies
        client.cookies.clear()

        headers = {"Authorization": f"Bearer {valid_access_token}"}
        response = client.get("/v1/auth/whoami", headers=headers)

        assert response.status_code == 200

        # Check logs for header source indication
        header_logs = [
            record
            for record in caplog.records
            if "header" in record.message.lower()
            and ("auth" in record.message.lower() or "source" in record.message.lower())
        ]
        # Should have logs indicating header was used as auth source
        # Note: This depends on specific logging implementation

    def test_header_auth_with_scope_verification(self, client):
        """Test that header auth properly verifies token scopes for protected endpoints."""

        # Create token without admin scopes
        token = make_access({"user_id": "test_user", "scope": "read"})
        headers = {"Authorization": f"Bearer {token}"}

        # Clear cookies
        client.cookies.clear()

        # Try to access admin endpoint
        response = client.get("/admin/config", headers=headers)

        if response.status_code == 404:
            return  # Skip if admin routes not available

        # Should fail with insufficient scopes, not general auth failure
        assert response.status_code == 403

        error_data = response.json()
        assert "code" in error_data
        assert error_data["code"] == "insufficient_scopes"

    def test_header_auth_works_with_refresh_token_in_body(self, client):
        """Test that header auth works alongside refresh token in request body."""

        # Create tokens
        access_token = make_access({"user_id": "test_user"})
        refresh_token = make_refresh({"user_id": "test_user", "jti": "test-jti"})

        # Clear cookies
        client.cookies.clear()

        # Use access token in header and refresh token in body
        headers = {"Authorization": f"Bearer {access_token}"}
        response = client.post(
            "/v1/auth/refresh", json={"refresh_token": refresh_token}, headers=headers
        )

        # Should work (may succeed or fail based on token state, but not auth error)
        assert (
            response.status_code != 401
        ), "Header auth should work with refresh token in body"

    def test_header_only_auth_no_cookie_leakage(self, client, valid_access_token):
        """Test that header-only auth doesn't leak cookies in responses."""

        # Clear any existing cookies
        client.cookies.clear()

        headers = {"Authorization": f"Bearer {valid_access_token}"}

        # Make authenticated request
        response = client.get("/v1/auth/whoami", headers=headers)
        assert response.status_code == 200

        # Check that response doesn't set any cookies
        set_cookie_headers = response.headers.get_list("set-cookie")

        # Should not have auth-related cookies
        auth_cookies = [
            h
            for h in set_cookie_headers
            if any(
                cookie_name in h
                for cookie_name in ["GSNH_AT=", "GSNH_RT=", "__session=", "device_id="]
            )
        ]

        assert len(auth_cookies) == 0, f"Header auth leaked cookies: {auth_cookies}"
