"""
Unit tests for the remaining protection endpoints that were fixed in the security audit.

Tests endpoints:
- /v1/care/* → require_auth_with_csrf (auth + CSRF on writes)
- /v1/admin/config-check → require_admin
- /v1/status/preflight and /v1/status/rate_limit → public (no auth, no CSRF)
- /v1/status/observability, /v1/status/vector_store, /v1/status/integrations → require_admin
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
import jwt
import time
import os

from app.main import create_app


def _create_jwt_token(scopes: list[str] = None) -> str:
    """Create a valid JWT token with specified scopes."""
    key = os.environ.get("JWT_SECRET", "x" * 64)
    now = int(time.time())
    payload = {"sub": "test_user", "iat": now, "exp": now + 3600}  # 1 hour expiry
    if scopes:
        payload["scopes"] = scopes
    return jwt.encode(payload, key, algorithm="HS256")


@pytest.fixture
def client():
    """Create test client with CSRF enabled."""
    # Set test environment - explicitly disable all test bypasses and require JWT
    jwt_secret = "x" * 64
    os.environ["JWT_SECRET"] = jwt_secret
    os.environ["ENV"] = "prod"  # Use prod to avoid dev-mode bypasses
    os.environ["REQUIRE_JWT"] = "true"  # Force JWT requirement
    os.environ["PYTEST_MODE"] = "false"
    os.environ["PYTEST_RUNNING"] = "false"
    os.environ["JWT_OPTIONAL_IN_TESTS"] = "false"
    os.environ["TEST_MODE"] = "false"
    os.environ["PYTEST_CURRENT_TEST"] = ""
    os.environ["DISABLE_AUTH_BYPASS"] = "true"
    os.environ["DEV_MODE"] = "false"  # Explicitly disable dev mode

    # Create app with explicit environment override
    app = create_app()

    # Double-check that JWT_SECRET is properly set in the app context
    print(f"DEBUG: JWT_SECRET in test fixture: {bool(os.environ.get('JWT_SECRET'))}")
    print(f"DEBUG: JWT_SECRET length: {len(os.environ.get('JWT_SECRET', ''))}")

    with TestClient(app) as test_client:
        # Set up CSRF token cookie
        csrf_token = "test_csrf_token_1234567890123456"
        test_client.cookies.set("csrf_token", csrf_token)
        test_client.headers.update({"X-CSRF-Token": csrf_token})
        yield test_client


@pytest.fixture
def auth_headers():
    """Headers for authenticated requests."""
    token = _create_jwt_token(["user:read"])
    return {
        "Authorization": f"Bearer {token}",
        "X-CSRF-Token": "test_csrf_token_1234567890123456"
    }


@pytest.fixture
def admin_auth_headers():
    """Headers for admin authenticated requests."""
    token = _create_jwt_token(["admin"])
    return {
        "Authorization": f"Bearer {token}",
        "X-CSRF-Token": "admin_csrf_token_1234567890123456"
    }


class TestCareEndpoints:
    """Test care endpoints protection."""

    def test_care_sessions_get_requires_auth(self, client):
        """GET /v1/care/sessions requires authentication."""
        response = client.get("/v1/care/sessions")
        assert response.status_code == 401

    def test_care_sessions_get_with_auth(self, client, auth_headers):
        """GET /v1/care/sessions works with authentication."""
        with patch("app.api.care.list_sessions_db", return_value=[]):
            response = client.get("/v1/care/sessions", headers=auth_headers)
            assert response.status_code == 200
            assert response.json() == {"items": []}

    def test_care_sessions_post_requires_auth_and_csrf(self, client):
        """POST /v1/care/sessions requires auth + CSRF."""
        response = client.post("/v1/care/sessions", json={"id": "test", "resident_id": "user1"})
        assert response.status_code == 401

    def test_care_sessions_post_requires_csrf(self, client, auth_headers):
        """POST /v1/care/sessions requires CSRF token."""
        # Remove CSRF token from headers to test CSRF requirement
        headers_without_csrf = {"Authorization": auth_headers["Authorization"]}
        response = client.post(
            "/v1/care/sessions",
            json={"id": "test", "resident_id": "user1"},
            headers=headers_without_csrf
        )
        assert response.status_code == 403

    def test_care_sessions_post_with_auth_and_csrf(self, client, auth_headers):
        """POST /v1/care/sessions works with auth + CSRF."""
        with patch("app.api.care.create_session"):
            response = client.post(
                "/v1/care/sessions",
                json={"id": "test", "resident_id": "user1"},
                headers=auth_headers
            )
            assert response.status_code == 200

    def test_care_sessions_patch_requires_auth_and_csrf(self, client):
        """PATCH /v1/care/sessions/{id} requires auth + CSRF."""
        response = client.patch("/v1/care/sessions/test123", json={"status": "updated"})
        assert response.status_code == 401

    def test_care_sessions_patch_with_auth_and_csrf(self, client, auth_headers):
        """PATCH /v1/care/sessions/{id} works with auth + CSRF."""
        with patch("app.api.care.update_session"):
            response = client.patch(
                "/v1/care/sessions/test123",
                json={"status": "updated"},
                headers=auth_headers
            )
            assert response.status_code == 200


class TestAdminEndpoints:
    """Test admin-only endpoints protection."""

    def test_admin_config_check_requires_auth(self, client):
        """GET /v1/admin/config-check requires authentication."""
        response = client.get("/v1/admin/config-check")
        print(f"Response status: {response.status_code}")
        print(f"Response content: {response.text[:200]}")
        # Debug: check why auth is bypassed
        if response.status_code == 200:
            print("DEBUG: Auth bypass detected - investigating...")
            # Check the response content for clues
            data = response.json()
            print(f"DEBUG: Response env: {data.get('env')}")
            print(f"DEBUG: Response dev_mode: {data.get('dev_mode')}")
        assert response.status_code == 401

    def test_admin_config_check_requires_admin(self, client, auth_headers):
        """GET /v1/admin/config-check requires admin privileges."""
        response = client.get("/v1/admin/config-check", headers=auth_headers)
        assert response.status_code == 403

    def test_admin_config_check_with_admin(self, client, admin_auth_headers):
        """GET /v1/admin/config-check works with admin auth."""
        response = client.get("/v1/admin/config-check", headers=admin_auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "env" in data
        assert "features" in data
        assert "security" in data


class TestStatusEndpoints:
    """Test status endpoints protection."""

    def test_status_preflight_public(self, client):
        """GET /v1/status/preflight is public."""
        response = client.get("/v1/status/preflight")
        assert response.status_code == 200
        data = response.json()
        assert "ok" in data
        assert "checks" in data

    def test_status_rate_limit_public(self, client):
        """GET /v1/status/rate_limit is public."""
        response = client.get("/v1/status/rate_limit")
        assert response.status_code == 200

    def test_status_observability_requires_auth(self, client):
        """GET /v1/status/observability requires authentication."""
        response = client.get("/v1/status/observability")
        assert response.status_code == 401

    def test_status_observability_requires_admin(self, client, auth_headers):
        """GET /v1/status/observability requires admin privileges."""
        response = client.get("/v1/status/observability", headers=auth_headers)
        assert response.status_code == 403

    def test_status_observability_with_admin(self, client, admin_auth_headers):
        """GET /v1/status/observability works with admin auth."""
        with patch("app.observability.get_ask_error_rate_by_backend", return_value={}):
            with patch("app.observability.get_ask_latency_p95_by_backend", return_value={}):
                response = client.get("/v1/status/observability", headers=admin_auth_headers)
                assert response.status_code == 200

    def test_status_vector_store_requires_auth(self, client):
        """GET /v1/status/vector_store requires authentication."""
        response = client.get("/v1/status/vector_store")
        assert response.status_code == 401

    def test_status_vector_store_requires_admin(self, client, auth_headers):
        """GET /v1/status/vector_store requires admin privileges."""
        response = client.get("/v1/status/vector_store", headers=auth_headers)
        assert response.status_code == 403

    def test_status_vector_store_with_admin(self, client, admin_auth_headers):
        """GET /v1/status/vector_store works with admin auth."""
        response = client.get("/v1/status/vector_store", headers=admin_auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "backend" in data

    def test_status_integrations_requires_auth(self, client):
        """GET /v1/status/integrations requires authentication."""
        response = client.get("/v1/status/integrations")
        assert response.status_code == 401

    def test_status_integrations_requires_admin(self, client, auth_headers):
        """GET /v1/status/integrations requires admin privileges."""
        response = client.get("/v1/status/integrations", headers=auth_headers)
        assert response.status_code == 403

    def test_status_integrations_with_admin(self, client, admin_auth_headers):
        """GET /v1/status/integrations works with admin auth."""
        with patch("app.status.integrations_status", return_value={"spotify": {"connected": True}}):
            response = client.get("/v1/status/integrations", headers=admin_auth_headers)
            assert response.status_code == 200
            data = response.json()
            assert "spotify" in data
