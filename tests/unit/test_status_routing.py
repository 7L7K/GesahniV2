"""
Tests for status endpoint routing and consolidation.

Verifies that:
1. Legacy /status redirects to /v1/status with 308
2. Canonical /v1/status/* endpoints return 200/401 as expected
3. OpenAPI schema only lists /v1/status/* endpoints, not legacy /status

Note: These tests require the route collision check to be mocked to avoid
unrelated health route conflicts during testing.
"""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


class TestStatusRouting:
    """Test status endpoint routing and redirects."""

    @pytest.fixture
    def app(self):
        """Create test app with status routes."""
        from app.main import create_app

        return create_app()

    @pytest.fixture
    def client(self, app):
        """Create test client."""
        return TestClient(app)

    def test_legacy_status_redirect(self, client):
        """Test that /status redirects to /v1/status with 308."""
        response = client.get("/status", follow_redirects=False)

        assert response.status_code == 308
        assert response.headers["location"] == "/v1/status"
        assert "redirect" in response.headers.get("location", "").lower()

    def test_legacy_status_follow_redirect(self, client):
        """Test that following /status redirect lands on /v1/status."""
        response = client.get("/status", follow_redirects=True)

        # Should get the actual status response, not a redirect
        assert response.status_code in [200, 401]  # 401 if auth required
        # Should not have location header when followed
        assert "location" not in response.headers

    def test_canonical_status_endpoint(self, client):
        """Test that /v1/status returns proper response."""
        response = client.get("/v1/status")

        # Should return actual status data or 401 if auth required
        assert response.status_code in [200, 401]
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, dict)
            # Should contain expected status fields
            expected_fields = ["backend", "ha", "llama", "gpt_quota", "metrics"]
            for field in expected_fields:
                assert field in data

    def test_status_budget_endpoint(self, client):
        """Test /v1/status/budget endpoint."""
        response = client.get("/v1/status/budget")

        assert response.status_code in [200, 401]  # 401 if auth required
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, dict)

    def test_status_ha_endpoint(self, client):
        """Test /v1/status/ha endpoint."""
        response = client.get("/v1/status/ha")

        assert response.status_code in [200, 401, 500]  # 500 if HA not available
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, dict)
            assert "status" in data

    def test_status_llama_endpoint(self, client):
        """Test /v1/status/llama endpoint."""
        response = client.get("/v1/status/llama")

        assert response.status_code in [200, 401, 500]  # 500 if Llama not available
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, dict)

    def test_status_features_endpoint(self, client):
        """Test /v1/status/features endpoint."""
        response = client.get("/v1/status/features")

        assert response.status_code in [200, 401]
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, dict)
            # Should contain feature flags
            expected_features = ["ha_enabled", "gpt_enabled", "vector_store"]
            for feature in expected_features:
                assert feature in data

    def test_status_vector_store_endpoint(self, client):
        """Test /v1/status/vector_store endpoint."""
        response = client.get("/v1/status/vector_store")

        assert response.status_code in [200, 401]
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, dict)
            assert "backend" in data

    def test_status_integrations_endpoint(self, client):
        """Test /v1/status/integrations endpoint."""
        response = client.get("/v1/status/integrations")

        assert response.status_code in [200, 401]
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, dict)
            # Should contain integration status
            expected_integrations = ["spotify", "google", "home_assistant"]
            for integration in expected_integrations:
                assert integration in data

    def test_status_rate_limit_endpoint(self, client):
        """Test /v1/status/rate_limit endpoint (public)."""
        response = client.get("/v1/status/rate_limit")

        # This endpoint should be public (no auth required)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
        assert "backend" in data

    def test_status_observability_endpoint(self, client):
        """Test /v1/status/observability endpoint (public)."""
        response = client.get("/v1/status/observability")

        # This endpoint should be public (no auth required)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
        assert "latency_p95_by_backend" in data
        assert "error_rate_by_backend" in data
        assert "timestamp" in data

    def test_budget_alias_still_works(self, client):
        """Test that legacy /v1/budget alias still works."""
        response = client.get("/v1/budget")

        assert response.status_code in [200, 401]  # 401 if auth required
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, dict)

    def test_legacy_budget_matches_canonical(self, client):
        """Test that /v1/budget and /v1/status/budget return same data."""
        response_alias = client.get("/v1/budget")
        response_canonical = client.get("/v1/status/budget")

        # Both should have same status code
        assert response_alias.status_code == response_canonical.status_code

        if response_alias.status_code == 200:
            data_alias = response_alias.json()
            data_canonical = response_canonical.json()
            # Should return same data structure
            assert data_alias == data_canonical

    @patch("app.main.create_app")
    def test_openapi_schema_excludes_legacy_status(self, mock_create_app, client):
        """Test that OpenAPI schema only includes /v1/status/* endpoints, not legacy /status."""
        # Get the OpenAPI schema
        response = client.get("/openapi.json")
        assert response.status_code == 200

        schema = response.json()
        paths = schema.get("paths", {})

        # Legacy /status should NOT be in schema (marked include_in_schema=False)
        assert "/status" not in paths

        # Canonical /v1/status endpoints SHOULD be in schema
        status_paths = [path for path in paths.keys() if path.startswith("/v1/status/")]
        assert len(status_paths) > 0, "No /v1/status/* paths found in OpenAPI schema"

        # Verify specific status endpoints are documented
        expected_status_paths = [
            "/v1/status",
            "/v1/status/budget",
            "/v1/status/ha",
            "/v1/status/llama",
            "/v1/status/features",
            "/v1/status/vector_store",
            "/v1/status/integrations",
            "/v1/status/rate_limit",
            "/v1/status/observability",
        ]

        documented_paths = set(paths.keys())
        for expected_path in expected_status_paths:
            assert (
                expected_path in documented_paths
            ), f"Missing {expected_path} in OpenAPI schema"
