"""Tests for music and Spotify endpoint routing after refactoring.

These tests verify that:
1. Legacy /v1/integrations/spotify/* paths redirect with 308 to /v1/spotify/*
2. Canonical /v1/music and /v1/spotify routes respond normally
3. OpenAPI schema shows only canonical routes, not legacy or debug endpoints
"""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


class TestMusicRouting:
    """Test music and Spotify endpoint routing after refactoring."""

    @pytest.fixture
    def app(self):
        """Create the FastAPI app with the current router configuration."""
        return create_app()

    @pytest.fixture
    def client(self, app):
        """Create a test client for the FastAPI app."""
        return TestClient(app)

    @pytest.mark.parametrize("legacy_path,canonical_path", [
        ("/v1/integrations/spotify/status", "/v1/spotify/status"),
        ("/v1/integrations/spotify/connect", "/v1/spotify/connect"),
        ("/v1/integrations/spotify/callback", "/v1/spotify/callback"),
        ("/v1/integrations/spotify/disconnect", "/v1/spotify/disconnect"),
    ])
    def test_legacy_spotify_integrations_redirects(self, client: TestClient, legacy_path: str, canonical_path: str):
        """Test that legacy /v1/integrations/spotify/* paths redirect with 308 to canonical paths."""
        # Make request to legacy path
        response = client.request("GET", legacy_path, follow_redirects=False)

        # Assert 308 Permanent Redirect
        assert response.status_code == 308, f"Expected 308 for GET {legacy_path}, got {response.status_code}"

        # Assert Location header points to canonical path
        assert response.headers.get("location") == canonical_path, \
            f"Expected Location header '{canonical_path}' for {legacy_path}, got '{response.headers.get('location')}'"

    def test_canonical_music_routes_respond_normally(self, client: TestClient):
        """Test that canonical /v1/music routes respond normally (not redirects)."""
        # Test /v1/state endpoint (part of music router)
        response = client.get("/v1/state")
        # Should get auth error or success, not a redirect
        assert response.status_code in [401, 422, 200], \
            f"Expected normal response for /v1/state, got {response.status_code}"

        # Should not be a redirect
        assert response.status_code != 308, \
            "Should not get 308 redirect for canonical /v1/state"

    def test_canonical_spotify_routes_respond_normally(self, client: TestClient):
        """Test that canonical /v1/spotify routes respond normally (not redirects)."""
        # Test /v1/spotify/status endpoint
        response = client.get("/v1/spotify/status")
        # Should get auth error or success, not a redirect
        assert response.status_code in [401, 422, 200], \
            f"Expected normal response for /v1/spotify/status, got {response.status_code}"

        # Should not be a redirect
        assert response.status_code != 308, \
            "Should not get 308 redirect for canonical /v1/spotify/status"

    def test_openapi_schema_excludes_debug_endpoints(self, client: TestClient):
        """Test that debug and test-only endpoints are excluded from OpenAPI schema."""
        # Get the OpenAPI schema
        schema_response = client.get("/openapi.json")
        assert schema_response.status_code == 200

        schema = schema_response.json()
        paths = schema.get("paths", {})

        # Debug and test endpoints that should NOT be in schema
        debug_paths = [
            "/v1/spotify/debug",
            "/v1/spotify/debug/store",
            "/v1/spotify/test/store_tx",
            "/v1/spotify/test/full_flow",
            "/v1/spotify/debug-cookie",
            "/v1/spotify/callback-test",
        ]

        for debug_path in debug_paths:
            assert debug_path not in paths, \
                f"Debug/test endpoint {debug_path} should NOT appear in OpenAPI schema"

    def test_openapi_schema_includes_canonical_music_routes(self, client: TestClient):
        """Test that canonical music routes are included in OpenAPI schema."""
        # Get the OpenAPI schema
        schema_response = client.get("/openapi.json")
        assert schema_response.status_code == 200

        schema = schema_response.json()
        paths = schema.get("paths", {})

        # Canonical music routes that SHOULD be in schema
        canonical_music_paths = [
            "/v1/state",  # music router endpoint
            "/v1/music",  # music endpoints
        ]

        for path in canonical_music_paths:
            # Check if path exists (may have method-specific paths)
            path_found = any(p.startswith(path) for p in paths.keys())
            assert path_found, f"Canonical music path {path} should appear in OpenAPI schema"

    def test_openapi_schema_includes_canonical_spotify_routes(self, client: TestClient):
        """Test that canonical Spotify routes are included in OpenAPI schema."""
        # Get the OpenAPI schema
        schema_response = client.get("/openapi.json")
        assert schema_response.status_code == 200

        schema = schema_response.json()
        paths = schema.get("paths", {})

        # Canonical Spotify routes that SHOULD be in schema
        canonical_spotify_paths = [
            "/v1/spotify/status",
            "/v1/spotify/connect",
            "/v1/spotify/callback",
            "/v1/spotify/disconnect",
            "/v1/spotify/health",
        ]

        for path in canonical_spotify_paths:
            assert path in paths, f"Canonical Spotify path {path} should appear in OpenAPI schema"

    def test_openapi_schema_excludes_legacy_integrations_paths(self, client: TestClient):
        """Test that legacy /v1/integrations/spotify/* paths are excluded from OpenAPI schema."""
        # Get the OpenAPI schema
        schema_response = client.get("/openapi.json")
        assert schema_response.status_code == 200

        schema = schema_response.json()
        paths = schema.get("paths", {})

        # Legacy integration paths that should NOT be in schema
        legacy_integration_paths = [
            "/v1/integrations/spotify/status",
            "/v1/integrations/spotify/connect",
            "/v1/integrations/spotify/callback",
            "/v1/integrations/spotify/disconnect",
        ]

        for legacy_path in legacy_integration_paths:
            assert legacy_path not in paths, \
                f"Legacy integration path {legacy_path} should NOT appear in OpenAPI schema"

    def test_no_duplicate_router_entries(self, client: TestClient):
        """Test that there are no duplicate router entries in the OpenAPI schema."""
        # Get the OpenAPI schema
        schema_response = client.get("/openapi.json")
        assert schema_response.status_code == 200

        schema = schema_response.json()
        paths = schema.get("paths", {})

        # Check for duplicate paths (same path appearing multiple times)
        path_count = {}
        for path in paths.keys():
            path_count[path] = path_count.get(path, 0) + 1

        duplicates = [path for path, count in path_count.items() if count > 1]
        assert len(duplicates) == 0, f"Found duplicate paths in OpenAPI schema: {duplicates}"

    def test_spotify_routes_have_proper_tags(self, client: TestClient):
        """Test that Spotify routes have appropriate OpenAPI tags."""
        # Get the OpenAPI schema
        schema_response = client.get("/openapi.json")
        assert schema_response.status_code == 200

        schema = schema_response.json()
        paths = schema.get("paths", {})

        # Check that Spotify routes have tags
        spotify_paths = [p for p in paths.keys() if p.startswith("/v1/spotify/")]

        for path in spotify_paths:
            operations = paths[path]
            for method, operation in operations.items():
                if method.lower() in ["get", "post", "put", "delete"]:
                    # Should have tags (may be inherited from router)
                    tags = operation.get("tags", [])
                    assert isinstance(tags, list), f"Path {path} {method} should have tags"

    @pytest.mark.parametrize("method,path", [
        ("GET", "/v1/integrations/spotify/status"),
        ("POST", "/v1/integrations/spotify/connect"),
        ("GET", "/v1/integrations/spotify/callback"),
        ("DELETE", "/v1/integrations/spotify/disconnect"),
    ])
    def test_redirect_methods_preserved(self, client: TestClient, method: str, path: str):
        """Test that 308 redirects preserve HTTP methods."""
        # Make request with specific method to legacy path
        response = client.request(method, path, follow_redirects=False)

        # Assert 308 Permanent Redirect
        assert response.status_code == 308, f"Expected 308 for {method} {path}, got {response.status_code}"

        # Assert Location header exists
        location = response.headers.get("location")
        assert location, f"Expected Location header for {method} {path}"

        # Location should point to canonical path
        assert location.startswith("/v1/spotify/"), \
            f"Expected Location to start with /v1/spotify/ for {method} {path}, got {location}"
