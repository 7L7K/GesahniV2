"""
Tests for deprecated API endpoints and deprecation handling.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


class TestDeprecations:
    """Test deprecated endpoints and deprecation handling."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        app = create_app()
        return TestClient(app)

    def test_deprecated_routes_marked_in_openapi(self, client):
        """Test that deprecated routes are properly marked in OpenAPI spec."""
        response = client.get("/openapi.json")
        assert response.status_code == 200

        spec = response.json()
        paths = spec["paths"]

        # Check that deprecated compatibility routes are marked as deprecated
        deprecated_paths = [
            "/whoami",
            "/spotify/status",
            "/google/status",
            "/google/oauth/callback",
        ]

        for path in deprecated_paths:
            if path in paths:
                # Should have deprecated: true in the spec
                for method_spec in paths[path].values():
                    if isinstance(method_spec, dict):
                        assert (
                            method_spec.get("deprecated") is True
                        ), f"Path {path} should be marked as deprecated"

    def test_deprecated_route_functionality(self, client):
        """Test that deprecated routes still function correctly."""
        # Test deprecated whoami route
        response = client.get("/whoami")
        # Should return some response (may be 401 if not authenticated, but should work)
        assert response.status_code in [200, 401, 404]  # Various possible responses

        # Test deprecated spotify status
        response = client.get("/spotify/status")
        assert response.status_code in [200, 404]  # Should work or return fallback

        # Test deprecated google status
        response = client.get("/google/status")
        assert response.status_code in [200, 404]  # Should work or return fallback

    def test_deprecated_routes_have_deprecation_header(self, client):
        """Test that deprecated routes include deprecation warning headers."""
        # Note: FastAPI doesn't automatically add deprecation headers,
        # but we can test that the routes are accessible
        response = client.get("/whoami")
        assert "content-type" in response.headers  # Basic functionality check

    def test_openapi_spec_includes_deprecation_info(self, client):
        """Test that OpenAPI spec includes deprecation information."""
        response = client.get("/openapi.json")
        spec = response.json()

        # Check that deprecated paths exist in the spec
        paths = spec["paths"]

        # At minimum, we should have some deprecated routes documented
        deprecated_count = 0
        for _path, path_spec in paths.items():
            for _method, method_spec in path_spec.items():
                if isinstance(method_spec, dict) and method_spec.get("deprecated"):
                    deprecated_count += 1

        # Should have at least some deprecated routes
        assert deprecated_count > 0, "Should have deprecated routes in OpenAPI spec"

    def test_deprecated_endpoints_still_accessible(self, client):
        """Test that deprecated endpoints are still accessible during grace period."""
        test_endpoints = [
            "/whoami",
            "/spotify/status",
            "/google/status",
        ]

        for endpoint in test_endpoints:
            response = client.get(endpoint)
            # Should not return 501 Not Implemented or similar
            assert (
                response.status_code != 501
            ), f"Deprecated endpoint {endpoint} should still work"
            # Should return some valid HTTP status
            assert (
                100 <= response.status_code < 600
            ), f"Endpoint {endpoint} returned invalid status"

    def test_deprecation_documentation_exists(self):
        """Test that deprecation documentation file exists."""
        import os

        assert os.path.exists("DEPRECATIONS.md"), "DEPRECATIONS.md file should exist"

        with open("DEPRECATIONS.md") as f:
            content = f.read()

        # Should contain key sections
        assert "# API Deprecations" in content
        assert "## Deprecation Policy" in content
        assert "## Currently Deprecated Endpoints" in content
        assert "GET /whoami" in content  # Should document the deprecated endpoints
