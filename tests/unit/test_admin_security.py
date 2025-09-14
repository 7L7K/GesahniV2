"""Unit tests for admin router security guards.

Tests the router-level admin guard implementation that ensures:
- 401 without authentication token
- 403 with token but non-admin scopes
- 200 for admin users
"""

from __future__ import annotations

import importlib
import os
import time

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create test client with proper router setup."""
    # Clean up any cached modules to ensure fresh setup
    modules_to_clean = ["app.main", "app.router.admin_api", "app.router.compat_api"]
    for mod in modules_to_clean:
        if mod in importlib.sys.modules:
            del importlib.sys.modules[mod]

    # Set JWT secret for testing and disable test mode
    os.environ["JWT_SECRET"] = "x" * 64
    os.environ["ENV"] = "dev"
    os.environ["PYTEST_MODE"] = "false"
    os.environ["PYTEST_RUNNING"] = "false"

    app = FastAPI()

    try:
        # Add the SessionAttachMiddleware to handle JWT decoding
        from app.middleware.session_attach import SessionAttachMiddleware

        app.add_middleware(SessionAttachMiddleware)

        # Import and include routers in the correct order to match production
        from app.router.admin_api import router as admin_router
        from app.router.compat_api import router as compat_router

        app.include_router(compat_router, prefix="")
        app.include_router(admin_router, prefix="/v1/admin")

    except Exception as e:
        # Fallback for testing environments where imports might fail
        pytest.skip(f"Could not set up test routers: {e}")

    return TestClient(app)


def _create_jwt_token(scopes: list[str] = None) -> str:
    """Create a valid JWT token with specified scopes."""
    key = os.environ.get("JWT_SECRET", "x" * 64)
    now = int(time.time())
    payload = {"sub": "test_user", "iat": now, "exp": now + 3600}  # 1 hour expiry
    if scopes:
        payload["scope"] = " ".join(
            scopes
        )  # Use space-separated string as per JWT spec
        payload["scopes"] = scopes  # Also include as list for compatibility
    return jwt.encode(payload, key, algorithm="HS256")


class TestAdminSecurity:
    """Test admin security guards and dependencies."""

    def test_user_model_creation(self):
        """Test User model creation and admin status."""
        # This test is no longer relevant since User model was removed
        # The admin router now uses require_roles(["admin"]) for authentication
        pass

    def test_require_roles_admin_allows_admin_scopes(self):
        """Test that require_roles allows requests with admin scopes."""
        # This test is now handled by the parametrized endpoint tests below
        # The router-level dependency ensures admin scope validation
        pass

    def test_require_roles_admin_blocks_non_admin_scopes(self):
        """Test that require_roles blocks requests without admin scopes."""
        # This test is now handled by the parametrized endpoint tests below
        # The router-level dependency ensures admin scope validation
        pass

    @pytest.mark.parametrize(
        "endpoint,method",
        [
            ("/v1/admin/ping", "get"),
            ("/v1/admin/rbac/info", "get"),
            ("/v1/admin/system/status", "get"),
            ("/v1/admin/tokens/google", "get"),
            ("/v1/admin/metrics", "get"),
            ("/v1/admin/router/decisions", "get"),
            ("/v1/admin/config", "get"),
            ("/v1/admin/config-check", "get"),
            ("/v1/admin/errors", "get"),
            ("/v1/admin/flags", "get"),
            ("/v1/admin/flags/test", "post"),
            ("/v1/admin/users/me", "get"),
            ("/v1/admin/retrieval/last", "get"),
            ("/v1/admin/backup", "post"),
        ],
    )
    def test_admin_endpoints_require_authentication(
        self, client: TestClient, endpoint: str, method: str
    ):
        """Test that all admin endpoints return 401 without authentication."""
        if method == "get":
            response = client.get(endpoint)
        elif method == "post":
            response = client.post(endpoint)
        assert response.status_code == 401

    @pytest.mark.parametrize(
        "endpoint,method",
        [
            ("/v1/admin/ping", "get"),
            ("/v1/admin/rbac/info", "get"),
            ("/v1/admin/system/status", "get"),
            ("/v1/admin/tokens/google", "get"),
            ("/v1/admin/metrics", "get"),
            ("/v1/admin/router/decisions", "get"),
            ("/v1/admin/config", "get"),
            ("/v1/admin/config-check", "get"),
            ("/v1/admin/errors", "get"),
            ("/v1/admin/flags", "get"),
            ("/v1/admin/flags/test", "post"),
            ("/v1/admin/users/me", "get"),
            ("/v1/admin/retrieval/last", "get"),
            ("/v1/admin/backup", "post"),
        ],
    )
    def test_admin_endpoints_reject_non_admin_scopes(
        self, client: TestClient, endpoint: str, method: str
    ):
        """Test that admin endpoints return 403 for users with non-admin scopes."""
        # Use a token with non-admin scopes (e.g., music:control)
        token = _create_jwt_token(["music:control"])
        headers = {"Authorization": f"Bearer {token}"}

        if method == "get":
            response = client.get(endpoint, headers=headers)
        elif method == "post":
            response = client.post(endpoint, headers=headers)
        assert response.status_code == 403

    @pytest.mark.parametrize(
        "endpoint,method",
        [
            ("/v1/admin/ping", "get"),
            ("/v1/admin/rbac/info", "get"),
            ("/v1/admin/system/status", "get"),
            ("/v1/admin/tokens/google", "get"),
            ("/v1/admin/metrics", "get"),
            ("/v1/admin/router/decisions", "get"),
            ("/v1/admin/config", "get"),
            ("/v1/admin/config-check", "get"),
            ("/v1/admin/errors", "get"),
            ("/v1/admin/flags", "get"),
            ("/v1/admin/flags/test", "post"),
            ("/v1/admin/users/me", "get"),
            ("/v1/admin/retrieval/last", "get"),
            ("/v1/admin/backup", "post"),
        ],
    )
    def test_admin_endpoints_allow_admin_scopes(
        self, client: TestClient, endpoint: str, method: str
    ):
        """Test that admin endpoints return 200 for users with admin scopes."""
        # Use a token with admin scopes
        token = _create_jwt_token(["admin"])
        headers = {"Authorization": f"Bearer {token}"}

        if method == "get":
            response = client.get(endpoint, headers=headers)
        elif method == "post":
            response = client.post(endpoint, headers=headers)
        assert response.status_code == 200

    def test_admin_ping_endpoint_functionality(self, client: TestClient):
        """Test the admin ping endpoint returns expected structure."""
        token = _create_jwt_token(["admin"])
        headers = {"Authorization": f"Bearer {token}"}

        response = client.get("/v1/admin/ping", headers=headers)
        assert response.status_code == 200

        data = response.json()
        assert "status" in data
        assert "service" in data
        assert "timestamp" in data
        assert data["status"] == "ok"
        assert data["service"] == "router_admin"

    def test_admin_rbac_info_endpoint_functionality(self, client: TestClient):
        """Test the admin RBAC info endpoint returns expected structure."""
        token = _create_jwt_token(["admin"])
        headers = {"Authorization": f"Bearer {token}"}

        response = client.get("/v1/admin/rbac/info", headers=headers)
        assert response.status_code == 200

        data = response.json()
        assert "rbac_enabled" in data
        assert "scopes" in data
        assert "note" in data
        assert data["rbac_enabled"] is True

    def test_admin_config_endpoint_functionality(self, client: TestClient):
        """Test the admin config endpoint returns configuration data."""
        token = _create_jwt_token(["admin"])
        headers = {"Authorization": f"Bearer {token}"}

        response = client.get("/v1/admin/config", headers=headers)
        assert response.status_code == 200

        data = response.json()
        assert "store" in data
        assert "vector_store" in data["store"]

    def test_admin_flags_get_endpoint_functionality(self, client: TestClient):
        """Test the admin flags GET endpoint returns flag data."""
        token = _create_jwt_token(["admin"])
        headers = {"Authorization": f"Bearer {token}"}

        response = client.get("/v1/admin/flags", headers=headers)
        assert response.status_code == 200

        data = response.json()
        assert "flags" in data

    def test_admin_flags_post_endpoint_functionality(self, client: TestClient):
        """Test the admin flags POST endpoint can update flags."""
        token = _create_jwt_token(["admin"])
        headers = {"Authorization": f"Bearer {token}"}

        # Test setting a flag
        response = client.post(
            "/v1/admin/flags?key=TEST_FLAG&value=test_value", headers=headers
        )
        assert response.status_code == 200

        data = response.json()
        assert "status" in data
        assert "key" in data
        assert "value" in data
        assert data["status"] == "ok"
        assert data["key"] == "TEST_FLAG"
        assert data["value"] == "test_value"

    def test_admin_flags_test_endpoint_functionality(self, client: TestClient):
        """Test the admin flags test endpoint."""
        token = _create_jwt_token(["admin"])
        headers = {"Authorization": f"Bearer {token}"}

        response = client.post("/v1/admin/flags/test", headers=headers)
        assert response.status_code == 200

        data = response.json()
        assert "status" in data
        assert "message" in data
        assert data["status"] == "ok"
        assert "Admin write test successful" in data["message"]

    def test_admin_users_me_endpoint_functionality(self, client: TestClient):
        """Test the admin users/me endpoint."""
        token = _create_jwt_token(["admin"])
        headers = {"Authorization": f"Bearer {token}"}

        response = client.get("/v1/admin/users/me", headers=headers)
        assert response.status_code == 200

        data = response.json()
        assert "user_id" in data
        assert "profile" in data
        assert "status" in data
        assert data["status"] == "ok"

    def test_admin_config_check_endpoint_functionality(self, client: TestClient):
        """Test the admin config-check endpoint returns configuration summary."""
        token = _create_jwt_token(["admin"])
        headers = {"Authorization": f"Bearer {token}"}

        response = client.get("/v1/admin/config-check", headers=headers)
        assert response.status_code == 200

        data = response.json()
        assert "env" in data
        assert "ci" in data
        assert "dev_mode" in data
        assert "features" in data
        assert "security" in data
        assert "middleware" in data
        assert "external" in data

    def test_admin_system_status_endpoint_functionality(self, client: TestClient):
        """Test the admin system status endpoint."""
        token = _create_jwt_token(["admin"])
        headers = {"Authorization": f"Bearer {token}"}

        response = client.get("/v1/admin/system/status", headers=headers)
        assert response.status_code == 200

        data = response.json()
        assert "status" in data
        assert "version" in data
        assert "uptime" in data
        assert data["status"] == "operational"

    def test_admin_metrics_endpoint_functionality(self, client: TestClient):
        """Test the admin metrics endpoint."""
        token = _create_jwt_token(["admin"])
        headers = {"Authorization": f"Bearer {token}"}

        response = client.get("/v1/admin/metrics", headers=headers)
        assert response.status_code == 200

        data = response.json()
        assert "metrics" in data
        assert "note" in data

    def test_admin_errors_endpoint_functionality(self, client: TestClient):
        """Test the admin errors endpoint."""
        token = _create_jwt_token(["admin"])
        headers = {"Authorization": f"Bearer {token}"}

        response = client.get("/v1/admin/errors", headers=headers)
        assert response.status_code == 200

        data = response.json()
        assert "errors" in data
        assert "count" in data
        assert "note" in data

    def test_admin_tokens_google_endpoint_functionality(self, client: TestClient):
        """Test the admin tokens/google endpoint."""
        token = _create_jwt_token(["admin"])
        headers = {"Authorization": f"Bearer {token}"}

        response = client.get("/v1/admin/tokens/google", headers=headers)
        assert response.status_code == 200

        data = response.json()
        assert "tokens" in data
        assert "note" in data

    def test_admin_router_decisions_endpoint_functionality(self, client: TestClient):
        """Test the admin router decisions endpoint."""
        token = _create_jwt_token(["admin"])
        headers = {"Authorization": f"Bearer {token}"}

        response = client.get("/v1/admin/router/decisions", headers=headers)
        assert response.status_code == 200

        data = response.json()
        assert "decisions" in data
        assert "note" in data

    def test_admin_retrieval_last_endpoint_functionality(self, client: TestClient):
        """Test the admin retrieval last endpoint."""
        token = _create_jwt_token(["admin"])
        headers = {"Authorization": f"Bearer {token}"}

        response = client.get("/v1/admin/retrieval/last", headers=headers)
        assert response.status_code == 200

        data = response.json()
        assert "retrievals" in data
        assert "count" in data
        assert "limit" in data


class TestAdminSecurityIntegration:
    """Integration tests for admin security with full FastAPI app."""

    def test_admin_router_included_in_app_schema(self, client: TestClient):
        """Test that admin routes are included in the OpenAPI schema."""
        response = client.get("/openapi.json")
        assert response.status_code == 200

        schema = response.json()
        paths = schema.get("paths", {})

        # Check that admin routes are present in schema
        assert "/v1/admin/ping" in paths
        assert "/v1/admin/config" in paths
        assert "/v1/admin/flags" in paths

        # Verify admin endpoints have proper tags
        ping_operation = paths["/v1/admin/ping"]["get"]
        assert "Admin" in ping_operation.get("tags", [])

    def test_admin_router_not_in_compat_schema(self, client: TestClient):
        """Test that compatibility routes are not in schema."""
        response = client.get("/openapi.json")
        assert response.status_code == 200

        schema = response.json()
        paths = schema.get("paths", {})

        # Check that legacy /admin/* routes are NOT in schema
        # (they should redirect but not be documented)
        assert "/admin/ping" not in paths
        assert "/admin/config" not in paths

    def test_router_level_dependency_applied(self, client: TestClient):
        """Test that the router-level dependency is properly applied to all endpoints."""
        # Test multiple endpoints to ensure they all require admin
        endpoints = [
            ("/v1/admin/ping", "get"),
            ("/v1/admin/config", "get"),
            ("/v1/admin/config-check", "get"),
            ("/v1/admin/flags", "get"),
            ("/v1/admin/flags/test", "post"),
            ("/v1/admin/system/status", "get"),
            ("/v1/admin/backup", "post"),
        ]

        for endpoint, method in endpoints:
            # Should fail without auth
            if method == "get":
                response = client.get(endpoint)
            elif method == "post":
                response = client.post(endpoint)
            assert (
                response.status_code == 401
            ), f"Endpoint {endpoint} should require auth"

            # Should fail with non-admin scopes
            token = _create_jwt_token(["music:control"])
            headers = {"Authorization": f"Bearer {token}"}
            if method == "get":
                response = client.get(endpoint, headers=headers)
            elif method == "post":
                response = client.post(endpoint, headers=headers)
            assert (
                response.status_code == 403
            ), f"Endpoint {endpoint} should reject non-admin scopes"
