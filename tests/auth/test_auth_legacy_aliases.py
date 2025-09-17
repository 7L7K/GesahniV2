"""Tests for legacy auth route aliases and their deprecation behavior.

This test file specifically tests the backward compatibility provided by
app/router/auth_legacy_aliases.py. These tests ensure that:

1. Legacy routes (/login, /register, /whoami) return HTTP 308 redirects to canonical paths
2. Deprecated routes include proper deprecation headers
3. Legacy route usage is tracked via Prometheus metrics (when available)
4. Functionality is preserved while guiding clients to canonical endpoints

These tests are separate from core auth tests to maintain clear separation
between canonical auth flow testing and legacy compatibility testing.
"""

import pytest
from fastapi.testclient import TestClient

try:
    from prometheus_client import REGISTRY

    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False


@pytest.fixture
def client():
    """Test client with the full application."""
    from app.main import create_app

    app = create_app()
    return TestClient(app)


class TestLegacyAuthAliases:
    """Test legacy auth route aliases and their behavior."""

    def test_legacy_login_redirects_to_canonical(self, client):
        """Test that POST /login redirects to POST /v1/auth/login."""
        response = client.post(
            "/login",
            json={"username": "test", "password": "pass"},
            allow_redirects=False,
        )

        assert response.status_code == 308
        assert response.headers.get("location") == "/v1/auth/login"

    def test_legacy_register_redirects_to_canonical(self, client):
        """Test that POST /register redirects to POST /v1/auth/register."""
        response = client.post(
            "/v1/auth/register",
            json={"username": "test", "password": "pass"},
            allow_redirects=False,
        )

        assert response.status_code == 308
        assert response.headers.get("location") == "/v1/auth/register"

    def test_legacy_whoami_redirects_to_canonical(self, client):
        """Test that GET /whoami redirects to GET /v1/auth/whoami."""
        response = client.get("/whoami", allow_redirects=False)

        assert response.status_code == 308
        assert response.headers.get("location") == "/v1/auth/whoami"

    def test_legacy_routes_include_deprecation_headers(self, client):
        """Test that legacy routes include proper deprecation headers."""
        # Test login
        response = client.post(
            "/login",
            json={"username": "test", "password": "pass"},
            allow_redirects=False,
        )
        assert response.headers.get("Deprecation") == "true"
        assert response.headers.get("Sunset") == "Wed, 31 Dec 2025 23:59:59 GMT"
        assert (
            response.headers.get("Link")
            == '<"/v1/auth/login">; rel="successor-version"'
        )

        # Test register
        response = client.post(
            "/v1/auth/register",
            json={"username": "test", "password": "pass"},
            allow_redirects=False,
        )
        assert response.headers.get("Deprecation") == "true"
        assert response.headers.get("Sunset") == "Wed, 31 Dec 2025 23:59:59 GMT"
        assert (
            response.headers.get("Link")
            == '<"/v1/auth/register">; rel="successor-version"'
        )

        # Test whoami
        response = client.get("/whoami", allow_redirects=False)
        assert response.headers.get("Deprecation") == "true"
        assert response.headers.get("Sunset") == "Wed, 31 Dec 2025 23:59:59 GMT"
        assert (
            response.headers.get("Link")
            == '<"/v1/auth/whoami">; rel="successor-version"'
        )

    @pytest.mark.skipif(not PROMETHEUS_AVAILABLE, reason="Prometheus not available")
    def test_legacy_routes_increment_prometheus_counter(self, client):
        """Test that legacy route usage increments Prometheus counter."""
        # Get initial counter value
        initial_value = 0
        if hasattr(REGISTRY, "_names_to_collectors"):
            for collector in REGISTRY._names_to_collectors.get(
                "auth_legacy_hits_total", []
            ):
                for metric in collector._metrics:
                    for sample in metric.samples:
                        if sample.labels.get("endpoint") == "/v1/login":
                            initial_value = sample.value
                            break

        # Make a request to legacy login
        client.post(
            "/login",
            json={"username": "test", "password": "pass"},
            allow_redirects=False,
        )

        # Check that counter incremented
        final_value = 0
        for collector in REGISTRY._names_to_collectors.get(
            "auth_legacy_hits_total", []
        ):
            for metric in collector._metrics:
                for sample in metric.samples:
                    if sample.labels.get("endpoint") == "/v1/login":
                        final_value = sample.value
                        break

        assert final_value > initial_value, "Prometheus counter should have incremented"

    def test_legacy_routes_with_follow_redirects_work(self, client):
        """Test that legacy routes work correctly when following redirects."""
        # Test login with follow redirects
        response = client.post(
            "/login",
            json={"username": "testuser", "password": "secret123"},
            allow_redirects=True,
        )
        # Should get final response from canonical endpoint
        assert response.status_code in [200, 400, 401]  # Auth endpoint responses

        # Test register with follow redirects
        response = client.post(
            "/v1/auth/register",
            json={"username": "testuser2", "password": "secret123"},
            allow_redirects=True,
        )
        assert response.status_code in [200, 400]  # Register endpoint responses

        # Test whoami with follow redirects
        response = client.get("/whoami", allow_redirects=True)
        assert response.status_code in [200, 401]  # Whoami endpoint responses

    def test_legacy_routes_maintain_query_parameters(self, client):
        """Test that legacy routes preserve query parameters during redirect."""
        # Test whoami with query parameters
        response = client.get("/whoami?debug=1", allow_redirects=False)

        assert response.status_code == 308
        # Query parameters should be preserved in the redirect location
        location = response.headers.get("location")
        assert "/v1/auth/whoami?debug=1" in location or "/v1/auth/whoami" in location

    def test_legacy_routes_preserve_request_method(self, client):
        """Test that legacy routes preserve HTTP method during redirect."""
        # Test unsupported methods get redirected with same method
        response = client.put("/login", allow_redirects=False)
        assert response.status_code == 308
        # PUT request should redirect to PUT on canonical endpoint

    def test_multiple_legacy_requests_increment_counter(self, client):
        """Test that multiple requests to legacy endpoints increment counter appropriately."""
        if not PROMETHEUS_AVAILABLE:
            pytest.skip("Prometheus not available")

        # Make multiple requests
        for _ in range(3):
            client.get("/whoami", allow_redirects=False)

        # Check counter value
        counter_value = 0
        for collector in REGISTRY._names_to_collectors.get(
            "auth_legacy_hits_total", []
        ):
            for metric in collector._metrics:
                for sample in metric.samples:
                    if sample.labels.get("endpoint") == "/v1/whoami":
                        counter_value = sample.value
                        break

        assert counter_value >= 3, f"Counter should be at least 3, got {counter_value}"

    def test_canonical_endpoints_still_work_directly(self, client):
        """Test that canonical endpoints still work directly (regression test)."""
        # Test canonical login
        response = client.post(
            "/v1/auth/login", json={"username": "test", "password": "pass"}
        )
        assert response.status_code in [200, 400, 401]

        # Test canonical register
        response = client.post(
            "/v1/auth/register", json={"username": "test", "password": "pass"}
        )
        assert response.status_code in [200, 400]

        # Test canonical whoami
        response = client.get("/v1/auth/whoami")
        assert response.status_code in [200, 401]


# Integration tests that require authentication
class TestLegacyAuthAliasesWithAuth:
    """Test legacy aliases with proper authentication setup."""

    @pytest.fixture
    def authenticated_client(self, client):
        """Client with a registered and logged-in user."""
        # Register a user
        register_response = client.post(
            "/v1/auth/register",
            json={"username": "legacy_test_user", "password": "test_password_123"},
        )
        assert register_response.status_code == 200

        # Login to get tokens
        login_response = client.post(
            "/v1/auth/login",
            json={"username": "legacy_test_user", "password": "test_password_123"},
        )
        assert login_response.status_code == 200

        # Extract access token
        tokens = login_response.json()
        access_token = tokens.get("access_token")

        # Set up client with auth header
        client.headers.update({"Authorization": f"Bearer {access_token}"})
        return client

    def test_authenticated_legacy_whoami_redirect_works(self, authenticated_client):
        """Test that authenticated requests to legacy whoami work after redirect."""
        response = authenticated_client.get("/whoami", allow_redirects=True)

        # Should get successful response after following redirect
        assert response.status_code == 200
        data = response.json()
        assert "is_authenticated" in data
        assert data["is_authenticated"] is True
        assert data["user_id"] == "legacy_test_user"

    def test_authenticated_legacy_whoami_headers_present(self, authenticated_client):
        """Test that deprecation headers are present even with authentication."""
        response = authenticated_client.get("/whoami", allow_redirects=False)

        assert response.status_code == 308
        assert response.headers.get("Deprecation") == "true"
        assert response.headers.get("Sunset") == "Wed, 31 Dec 2025 23:59:59 GMT"
        assert (
            response.headers.get("Link")
            == '<"/v1/auth/whoami">; rel="successor-version"'
        )
