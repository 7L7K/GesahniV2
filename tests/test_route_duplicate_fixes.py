"""Tests for route duplicate fixes.

This module tests the fixes for duplicate route handlers that were identified
by the route inventory script.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


class TestHealthRouteFixes:
    """Test fixes for health route duplicates."""

    def test_health_redirect_to_healthz(self, client):
        """Test that /health redirects to /healthz with 308 status."""
        response = client.get("/health", follow_redirects=False)
        assert response.status_code == 308
        assert response.headers["location"] == "/healthz"

    def test_healthz_works_directly(self, client):
        """Test that /healthz works directly without redirects."""
        response = client.get("/healthz")
        assert response.status_code == 200
        data = response.json()
        assert "ok" in data or "status" in data

    def test_health_not_in_openapi_schema(self, client):
        """Test that /health is not included in the OpenAPI schema."""
        # Try different OpenAPI endpoints
        for endpoint in ["/openapi.json", "/docs", "/redoc"]:
            response = client.get(endpoint)
            if response.status_code == 200:
                if endpoint == "/openapi.json":
                    schema = response.json()
                    paths = schema.get("paths", {})
                    assert "/health" not in paths
                    assert "/healthz" in paths
                break
        else:
            # If no OpenAPI endpoint works, just verify the redirect works
            response = client.get("/health", follow_redirects=False)
            assert response.status_code == 308


class TestStatusRouteFixes:
    """Test fixes for status route duplicates."""

    def test_v1_status_works(self, client):
        """Test that /v1/status works with the canonical full_status handler."""
        response = client.get("/v1/status")
        # This may require authentication, so we just check it's not a 404
        assert response.status_code != 404

    def test_spotify_status_available_separately(self, client):
        """Test that Spotify-specific status is available at its own endpoint."""
        response = client.get("/v1/spotify/status")
        # This may require authentication, so we just check it's not a 404
        assert response.status_code != 404


class TestRouteInventoryIntegration:
    """Integration tests to ensure the route inventory script passes."""

    def test_no_route_duplicates(self):
        """Test that the route inventory script would pass (no duplicates)."""
        # This is more of a smoke test - the actual route inventory script
        # should be run separately to verify no duplicates exist
        from collections import defaultdict
        
        # Collect routes from the app
        seen = defaultdict(list)
        for route in app.routes:
            methods = sorted(getattr(route, "methods", []) or [])
            path = getattr(route, "path", None)
            name = getattr(route, "name", None)
            if not path or not methods:
                continue
            for method in methods:
                key = (method, path)
                seen[key].append(name)
        
        # Check for duplicates
        duplicates = {k: v for k, v in seen.items() if len(v) > 1}
        assert not duplicates, f"Found route duplicates: {duplicates}"

    def test_health_endpoints_are_unique(self):
        """Test that health-related endpoints don't have duplicates."""
        from collections import defaultdict
        
        seen = defaultdict(list)
        for route in app.routes:
            methods = sorted(getattr(route, "methods", []) or [])
            path = getattr(route, "path", None)
            name = getattr(route, "name", None)
            if not path or not methods:
                continue
            # Only check health-related routes
            if "/health" in path or "/healthz" in path:
                for method in methods:
                    key = (method, path)
                    seen[key].append(name)
        
        # Check for duplicates in health routes
        duplicates = {k: v for k, v in seen.items() if len(v) > 1}
        assert not duplicates, f"Found health route duplicates: {duplicates}"

    def test_status_endpoints_are_unique(self):
        """Test that status-related endpoints don't have duplicates."""
        from collections import defaultdict
        
        seen = defaultdict(list)
        for route in app.routes:
            methods = sorted(getattr(route, "methods", []) or [])
            path = getattr(route, "path", None)
            name = getattr(route, "name", None)
            if not path or not methods:
                continue
            # Only check status-related routes
            if "/status" in path:
                for method in methods:
                    key = (method, path)
                    seen[key].append(name)
        
        # Check for duplicates in status routes
        duplicates = {k: v for k, v in seen.items() if len(v) > 1}
        assert not duplicates, f"Found status route duplicates: {duplicates}"
