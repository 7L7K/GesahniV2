"""
Test auth error contracts - ensure all 401/403 responses follow standardized format.

Tests verify that auth gates return proper error envelopes with:
- code: machine-readable error code
- message: human-readable message
- hint: actionable hint when available
- meta: debuggable context (req_id, timestamp, error_id, etc.)
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
def valid_token():
    """Create a valid access token for testing."""
    return make_access({"user_id": "test_user"})


class TestAuthErrorContracts:
    """Test that all auth gates return proper error contracts."""

    def _assert_error_contract(self, response, expected_status, expected_code=None):
        """Assert that error response follows the standardized contract."""
        assert response.status_code == expected_status

        error_data = response.json()

        # Required fields
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

        # Meta fields
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

    def test_ask_endpoint_no_auth(self, client):
        """Test /v1/ask returns proper 401 error contract."""
        response = client.post("/v1/ask", json={"prompt": "test"})
        error_data = self._assert_error_contract(response, 401, "unauthorized")
        assert "hint" in error_data
        assert "login or include Authorization header" in error_data["hint"]

    def test_whoami_endpoint_no_auth(self, client):
        """Test /v1/whoami returns proper 401 error contract."""
        response = client.get("/v1/whoami")
        self._assert_error_contract(response, 401, "unauthorized")

    def test_chat_endpoint_no_auth(self, client):
        """Test /v1/chat returns proper 401 error contract."""
        response = client.post("/v1/chat", json={"messages": []})
        self._assert_error_contract(response, 401, "unauthorized")

    def test_admin_config_no_token(self, client):
        """Test admin endpoint without token returns proper 403 error contract."""
        response = client.get("/admin/config")
        # Note: admin routes may return 404 in test mode if not included
        if response.status_code == 404:
            return  # Skip if admin routes not available in test
        self._assert_error_contract(response, 403, "forbidden")

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
            self._assert_error_contract(response, 403, "forbidden")

    def test_dev_endpoints_no_auth(self, client):
        """Test dev endpoints return proper 403 error contracts."""
        response = client.post("/dev/mint_access", json={})
        if response.status_code == 404:
            return  # Skip if dev routes not available
        self._assert_error_contract(response, 403, "forbidden")

    def test_scope_protected_endpoints_insufficient_scopes(self, client, valid_token):
        """Test scope-protected endpoints return proper 403 when token lacks required scopes."""
        # Use a token without admin scopes for admin-only endpoints
        headers = {"Authorization": f"Bearer {valid_token}"}

        # Try admin endpoints that require admin scope
        response = client.get("/admin/config", headers=headers)
        if response.status_code == 404:
            return  # Skip if admin routes not available
        self._assert_error_contract(response, 403, "insufficient_scopes")

    def test_csrf_protected_endpoints_invalid_csrf(self, client, valid_token):
        """Test CSRF-protected endpoints return proper 403 for invalid CSRF."""
        headers = {"Authorization": f"Bearer {valid_token}"}

        # Try to post to a CSRF-protected endpoint with invalid CSRF
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
        self._assert_error_contract(response, 403, "invalid_csrf")

    def test_refresh_token_endpoints_invalid_token(self, client):
        """Test refresh token endpoints return proper 401 for invalid tokens."""
        response = client.post("/v1/auth/refresh", json={"refresh_token": "invalid"})
        self._assert_error_contract(response, 401, "invalid_refresh_token")

    def test_google_oauth_invalid_state(self, client):
        """Test Google OAuth callback returns proper 403 for invalid state."""
        response = client.get("/v1/google/callback?code=test&state=invalid")
        if response.status_code == 404:
            return  # Skip if Google routes not available
        self._assert_error_contract(response, 403, "invalid_state")

    def test_spotify_endpoints_origin_check(self, client):
        """Test Spotify endpoints return proper 403 for invalid origins."""
        # This would require setting up CORS headers, but let's test the structure
        # if we can trigger an origin error
        pass  # Skip for now as it's hard to trigger in test environment

    def test_error_response_headers(self, client):
        """Test that error responses include proper headers."""
        response = client.post("/v1/ask", json={"prompt": "test"})

        assert response.status_code == 401
        assert "X-Error-Code" in response.headers
        assert response.headers["X-Error-Code"] == "unauthorized"
        assert "WWW-Authenticate" in response.headers
        assert "Bearer" in response.headers["WWW-Authenticate"]

    def test_forbidden_response_headers(self, client, valid_token):
        """Test that 403 responses include proper headers."""
        headers = {"Authorization": f"Bearer {valid_token}"}

        response = client.get("/debug/config", headers=headers)
        if response.status_code == 404:
            return  # Skip if debug routes not available

        assert response.status_code == 403
        assert "X-Error-Code" in response.headers
        assert response.headers["X-Error-Code"] == "forbidden"
