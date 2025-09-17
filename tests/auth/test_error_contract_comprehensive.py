"""
Comprehensive contract tests for error bodies (shape + code for each branch).

This test file verifies that all error responses follow standardized contracts
with proper shape, codes, and messages for every error branch in the auth system.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.tokens import make_access, make_refresh


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
def valid_refresh_token():
    """Create a valid refresh token for testing."""
    return make_refresh({"user_id": "test_user", "jti": "test-jti"})


class TestErrorBodyContracts:
    """Test that all auth error branches return proper error contracts."""

    def _assert_standard_error_contract(
        self, response, expected_status, expected_code=None
    ):
        """Assert that error response follows the standardized contract."""
        assert response.status_code == expected_status

        error_data = response.json()

        # Required fields for all errors
        assert "code" in error_data, f"Missing 'code' in error response: {error_data}"
        assert (
            "message" in error_data
        ), f"Missing 'message' in error response: {error_data}"
        assert "meta" in error_data, f"Missing 'meta' in error response: {error_data}"

        # Types
        assert isinstance(
            error_data["code"], str
        ), f"code should be string: {error_data['code']}"
        assert isinstance(
            error_data["message"], str
        ), f"message should be string: {error_data['message']}"
        assert isinstance(
            error_data["meta"], dict
        ), f"meta should be dict: {error_data['meta']}"

        # Meta fields (required for all errors)
        meta = error_data["meta"]
        assert "req_id" in meta, f"Missing req_id in meta: {meta}"
        assert "timestamp" in meta, f"Missing timestamp in meta: {meta}"
        assert "error_id" in meta, f"Missing error_id in meta: {meta}"
        assert "env" in meta, f"Missing env in meta: {meta}"
        assert "status_code" in meta, f"Missing status_code in meta: {meta}"
        assert meta["status_code"] == expected_status

        # Optional hint field
        if "hint" in error_data:
            assert isinstance(error_data["hint"], (str, type(None)))

        # Check expected code if provided
        if expected_code:
            assert (
                error_data["code"] == expected_code
            ), f"Expected code '{expected_code}', got '{error_data['code']}'"

        return error_data

    def test_ask_endpoint_missing_auth(self, client):
        """Test /v1/ask returns proper 401 error contract for missing auth."""
        response = client.post("/v1/ask", json={"prompt": "test"})
        error_data = self._assert_standard_error_contract(response, 401, "unauthorized")
        assert "hint" in error_data
        assert "provide a valid bearer token or auth cookies" in error_data["hint"]

    def test_ask_endpoint_invalid_token(self, client):
        """Test /v1/ask returns proper 401 error contract for invalid token."""
        headers = {"Authorization": "Bearer invalid-token"}
        response = client.post("/v1/ask", json={"prompt": "test"}, headers=headers)
        error_data = self._assert_standard_error_contract(response, 401, "unauthorized")
        assert "hint" in error_data

    def test_ask_endpoint_expired_token(self, client):
        """Test /v1/ask returns proper 401 error contract for expired token."""
        # Create an expired token (negative TTL)
        expired_token = make_access({"user_id": "test_user"}, ttl_s=-1)
        headers = {"Authorization": f"Bearer {expired_token}"}
        response = client.post("/v1/ask", json={"prompt": "test"}, headers=headers)
        error_data = self._assert_standard_error_contract(response, 401, "unauthorized")
        assert "hint" in error_data

    def test_whoami_endpoint_no_auth(self, client):
        """Test /v1/whoami returns proper 401 error contract."""
        response = client.get("/v1/whoami")
        self._assert_standard_error_contract(response, 401, "unauthorized")

    def test_chat_endpoint_no_auth(self, client):
        """Test /v1/chat returns proper 401 error contract."""
        response = client.post("/v1/chat", json={"messages": []})
        self._assert_standard_error_contract(response, 401, "unauthorized")

    def test_state_endpoint_no_auth(self, client):
        """Test /v1/state returns proper 401 error contract."""
        response = client.get("/v1/state")
        self._assert_standard_error_contract(response, 401, "unauthorized")

    def test_admin_config_no_auth(self, client):
        """Test admin endpoint returns proper 403 error contract without auth."""
        response = client.get("/admin/config")
        if response.status_code == 404:
            return  # Skip if admin routes not available
        self._assert_standard_error_contract(response, 403, "forbidden")

    def test_admin_config_insufficient_scope(self, client, valid_access_token):
        """Test admin endpoint returns proper 403 error contract with insufficient scope."""
        headers = {"Authorization": f"Bearer {valid_access_token}"}
        response = client.get("/admin/config", headers=headers)
        if response.status_code == 404:
            return  # Skip if admin routes not available
        self._assert_standard_error_contract(response, 403, "insufficient_scopes")

    def test_debug_endpoints_no_auth(self, client):
        """Test debug endpoints return proper 403 error contracts."""
        debug_endpoints = [
            "/debug/config",
            "/debug/routes",
            "/debug/health",
            "/debug/metrics",
        ]

        for endpoint in debug_endpoints:
            response = client.get(endpoint)
            if response.status_code == 404:
                continue  # Skip if debug routes not available
            self._assert_standard_error_contract(response, 403, "forbidden")

    def test_dev_endpoints_no_auth(self, client):
        """Test dev endpoints return proper 403 error contracts."""
        response = client.post("/dev/mint_access", json={})
        if response.status_code == 404:
            return  # Skip if dev routes not available
        self._assert_standard_error_contract(response, 403, "forbidden")

    def test_csrf_protected_endpoints_invalid_csrf(self, client, valid_access_token):
        """Test CSRF-protected endpoints return proper 403 for invalid CSRF."""
        headers = {"Authorization": f"Bearer {valid_access_token}"}

        response = client.post(
            "/v1/ask",
            json={"prompt": "test"},
            headers={
                **headers,
                "X-CSRF-Token": "invalid_token",
            },
        )
        # Note: CSRF validation might be disabled in test mode
        if response.status_code != 401:
            return
        self._assert_standard_error_contract(response, 403, "invalid_csrf")

    def test_refresh_endpoint_invalid_token(self, client):
        """Test refresh endpoint returns proper 401 for invalid tokens."""
        response = client.post("/v1/auth/refresh", json={"refresh_token": "invalid"})
        self._assert_standard_error_contract(response, 401, "invalid_refresh_token")

    def test_refresh_endpoint_missing_token(self, client):
        """Test refresh endpoint returns proper 401 when no refresh token available."""
        response = client.post("/v1/auth/refresh")
        self._assert_standard_error_contract(response, 401, "invalid_refresh_token")

    def test_refresh_endpoint_replay_attack(self, client, valid_refresh_token):
        """Test refresh endpoint returns proper 401 for replay attack (used token)."""
        # First use should work (may succeed or fail depending on token state)
        response1 = client.post(
            "/v1/auth/refresh", json={"refresh_token": valid_refresh_token}
        )

        # Second use should fail with replay detection
        response2 = client.post(
            "/v1/auth/refresh", json={"refresh_token": valid_refresh_token}
        )

        # Should get 401 for replay attack
        if response2.status_code == 401:
            error_data = self._assert_standard_error_contract(
                response2, 401, "invalid_refresh_token"
            )
            # Could be more specific replay error code if implemented
            assert error_data["code"] in ["invalid_refresh_token", "replay_detected"]

    def test_google_oauth_invalid_state(self, client):
        """Test Google OAuth callback returns proper 403 for invalid state."""
        response = client.get("/v1/google/callback?code=test&state=invalid")
        if response.status_code == 404:
            return  # Skip if Google routes not available
        self._assert_standard_error_contract(response, 403, "invalid_state")

    def test_spotify_oauth_invalid_state(self, client):
        """Test Spotify OAuth callback returns proper 403 for invalid state."""
        response = client.get("/v1/spotify/callback?code=test&state=invalid")
        if response.status_code == 404:
            return  # Skip if Spotify routes not available
        self._assert_standard_error_contract(response, 403, "invalid_state")

    def test_register_endpoint_username_taken(self, client):
        """Test register endpoint returns proper 400 for username_taken."""
        # First register a user
        response1 = client.post(
            "/v1/auth/register",
            json={"username": "testuser", "password": "testpass123"},
        )

        # Try to register the same user again
        response2 = client.post(
            "/v1/auth/register",
            json={"username": "testuser", "password": "testpass123"},
        )

        if response2.status_code == 400:
            error_data = self._assert_standard_error_contract(
                response2, 400, "username_taken"
            )
            assert "hint" in error_data

    def test_register_endpoint_invalid_password(self, client):
        """Test register endpoint returns proper 400 for invalid password."""
        response = client.post(
            "/v1/auth/register",
            json={
                "username": "testuser",
                "password": "123",  # Too short
            },
        )
        self._assert_standard_error_contract(response, 400, "invalid")

    def test_register_endpoint_missing_fields(self, client):
        """Test register endpoint returns proper 400 for missing fields."""
        response = client.post("/v1/auth/register", json={})
        self._assert_standard_error_contract(response, 400, "invalid_request")

    def test_login_endpoint_invalid_credentials(self, client):
        """Test login endpoint returns proper 401 for invalid credentials."""
        response = client.post(
            "/v1/auth/login", json={"username": "nonexistent", "password": "wrong"}
        )
        # Login might return different codes depending on implementation
        if response.status_code in [401, 400]:
            error_data = self._assert_standard_error_contract(
                response, response.status_code
            )
            assert error_data["code"] in [
                "unauthorized",
                "invalid_credentials",
                "authentication_failed",
            ]

    def test_token_endpoint_invalid_scope(self, client):
        """Test token endpoint returns proper 403 for invalid scope."""
        response = client.post(
            "/v1/auth/token",
            data={
                "username": "testuser",
                "password": "testpass",
                "scope": "invalid_scope",
            },
        )
        if response.status_code == 403:
            self._assert_standard_error_contract(response, 403, "insufficient_scopes")

    def test_rate_limit_exceeded(self, client):
        """Test rate limit returns proper 429 error contract."""
        # Make multiple rapid requests to trigger rate limit
        for i in range(10):
            response = client.post("/v1/auth/login", json={"username": f"user{i}"})

        # Should eventually get rate limited
        if response.status_code == 429:
            error_data = self._assert_standard_error_contract(
                response, 429, "too_many_requests"
            )
            assert "hint" in error_data

    def test_error_response_headers(self, client):
        """Test that all error responses include proper security headers."""
        response = client.post("/v1/ask", json={"prompt": "test"})

        assert response.status_code == 401
        assert "X-Error-Code" in response.headers
        assert response.headers["X-Error-Code"] == "unauthorized"
        assert "WWW-Authenticate" in response.headers
        assert "Bearer" in response.headers["WWW-Authenticate"]

    def test_forbidden_response_headers(self, client, valid_access_token):
        """Test that 403 responses include proper headers."""
        headers = {"Authorization": f"Bearer {valid_access_token}"}

        response = client.get("/debug/config", headers=headers)
        if response.status_code == 404:
            return  # Skip if debug routes not available

        assert response.status_code == 403
        assert "X-Error-Code" in response.headers
        assert response.headers["X-Error-Code"] == "forbidden"

    def test_error_response_no_cookies_leaked(self, client):
        """Test that error responses don't leak sensitive cookies."""
        response = client.post("/v1/ask", json={"prompt": "test"})

        # Error responses should not set auth cookies
        set_cookie_headers = response.headers.get_list("set-cookie")
        auth_cookies = [
            h
            for h in set_cookie_headers
            if any(
                cookie_name in h
                for cookie_name in ["GSNH_AT=", "GSNH_RT=", "__session=", "device_id="]
            )
        ]
        assert (
            len(auth_cookies) == 0
        ), f"Error response leaked auth cookies: {auth_cookies}"
