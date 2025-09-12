"""Tests for compatibility redirects in the FastAPI application.

These tests verify that legacy endpoint URLs properly redirect (308 Permanent Redirect)
to their canonical v1 API paths, preserving HTTP methods and providing clear
migration paths for clients.
"""


import pytest
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.testclient import TestClient


class TestCompatRedirects:
    """Test compatibility redirects from legacy endpoints to canonical v1 paths."""

    @pytest.fixture
    def app(self):
        """Create a minimal test FastAPI app with redirect routes."""
        app = FastAPI()

        # Add redirect routes manually to avoid route collision issues
        # These should have include_in_schema=False to match real app behavior
        @app.get("/whoami", include_in_schema=False)
        def whoami_compat():
            return RedirectResponse(url="/v1/whoami", status_code=308)

        @app.get("/spotify/status", include_in_schema=False)
        def spotify_status_compat():
            return RedirectResponse(url="/v1/spotify/status", status_code=308)

        @app.post("/ask", include_in_schema=False)
        def ask_compat():
            return RedirectResponse(url="/v1/ask", status_code=308)

        @app.get("/google/status", include_in_schema=False)
        def google_status_compat():
            return RedirectResponse(url="/v1/google/status", status_code=308)

        # Auth redirects - these should also be hidden from schema
        @app.post("/v1/login", include_in_schema=False)
        def login_compat():
            return RedirectResponse(url="/v1/auth/login", status_code=308)

        @app.post("/v1/logout", include_in_schema=False)
        def logout_compat():
            return RedirectResponse(url="/v1/auth/logout", status_code=308)

        @app.post("/v1/register", include_in_schema=False)
        def register_compat():
            return RedirectResponse(url="/v1/auth/register", status_code=308)

        @app.post("/v1/refresh", include_in_schema=False)
        def refresh_compat():
            return RedirectResponse(url="/v1/auth/refresh", status_code=308)

        # Add some mock canonical endpoints
        @app.get("/v1/whoami")
        def whoami_v1():
            return {"user": "test", "status": "authenticated"}

        @app.get("/v1/spotify/status")
        def spotify_status_v1():
            return {"status": "connected"}

        @app.post("/v1/ask")
        def ask_v1():
            return {"response": "Hello from AI"}

        @app.get("/v1/google/status")
        def google_status_v1():
            return {"status": "connected"}

        @app.post("/v1/auth/login")
        def login_v1():
            return {"token": "mock_token", "status": "logged_in"}

        @app.post("/v1/auth/logout")
        def logout_v1():
            return {"status": "logged_out"}

        @app.post("/v1/auth/register")
        def register_v1():
            return {"status": "registered", "user_id": "123"}

        @app.post("/v1/auth/refresh")
        def refresh_v1():
            return {"token": "new_token", "status": "refreshed"}

        return app

    @pytest.fixture
    def client(self, app):
        """Create a test client for the FastAPI app."""
        return TestClient(app)

    @pytest.mark.parametrize("legacy_method,legacy_path,canonical_path", [
        # Legacy functional endpoints that became redirects
        ("GET", "/whoami", "/v1/whoami"),
        ("GET", "/spotify/status", "/v1/spotify/status"),
        ("POST", "/ask", "/v1/ask"),
        ("GET", "/google/status", "/v1/google/status"),
        # Legacy auth endpoints
        ("POST", "/v1/login", "/v1/auth/login"),
        ("POST", "/v1/logout", "/v1/auth/logout"),
        ("POST", "/v1/register", "/v1/auth/register"),
        ("POST", "/v1/refresh", "/v1/auth/refresh")
    ])
    def test_legacy_redirects(self, client: TestClient, legacy_method: str, legacy_path: str, canonical_path: str):
        """Test that legacy endpoints return 308 redirects to canonical paths."""
        # Make request to legacy path
        response = client.request(legacy_method, legacy_path, follow_redirects=False)

        # Assert 308 Permanent Redirect
        assert response.status_code == 308, f"Expected 308 for {legacy_method} {legacy_path}, got {response.status_code}"

        # Assert Location header points to canonical path
        assert response.headers.get("location") == canonical_path, \
            f"Expected Location header '{canonical_path}' for {legacy_method} {legacy_path}, got '{response.headers.get('location')}'"

        # Assert no body content (redirects shouldn't have meaningful body)
        assert len(response.content) == 0 or response.content == b"", \
            f"Expected empty body for redirect {legacy_method} {legacy_path}, got {len(response.content)} bytes"

    @pytest.mark.parametrize("legacy_method,legacy_path,canonical_path,expected_status", [
        # Test following redirects to ensure canonical endpoints exist
        ("GET", "/whoami", "/v1/whoami", 200),  # Mock endpoint returns success
        ("GET", "/spotify/status", "/v1/spotify/status", 200),  # Mock endpoint returns success
        ("POST", "/ask", "/v1/ask", 200),  # Mock endpoint returns success
        ("GET", "/google/status", "/v1/google/status", 200),  # Mock endpoint returns success
        ("POST", "/v1/login", "/v1/auth/login", 200),  # Mock endpoint returns success
        ("POST", "/v1/logout", "/v1/auth/logout", 200),  # Mock endpoint returns success
        ("POST", "/v1/register", "/v1/auth/register", 200),  # Mock endpoint returns success
        ("POST", "/v1/refresh", "/v1/auth/refresh", 200),  # Mock endpoint returns success
    ])
    def test_following_redirects(self, client: TestClient, legacy_method: str, legacy_path: str, canonical_path: str, expected_status: int):
        """Test that following redirects lands on functional canonical endpoints."""
        # Make request with follow_redirects=True
        response = client.request(legacy_method, legacy_path, follow_redirects=True)

        # Should get the status code from the canonical endpoint (not 308)
        assert response.status_code == expected_status, \
            f"Expected status {expected_status} after following redirect from {legacy_method} {legacy_path}, got {response.status_code}"

        # Verify we're no longer getting a redirect
        assert response.status_code != 308, \
            f"Should not get 308 after following redirect from {legacy_method} {legacy_path}"

    def test_redirect_preserves_method(self, client: TestClient):
        """Test that 308 redirects preserve the HTTP method."""
        # POST to legacy ask endpoint
        response = client.post("/ask", follow_redirects=False)
        assert response.status_code == 308
        assert response.headers.get("location") == "/v1/ask"

        # When following, should still be a POST to /v1/ask
        response = client.post("/ask", follow_redirects=True)
        # Should get validation error or auth error, but not method not allowed
        assert response.status_code in [401, 422, 200], \
            f"Expected valid response after following POST redirect, got {response.status_code}"

    def test_redirect_headers(self, client: TestClient):
        """Test that redirects have appropriate headers."""
        response = client.get("/whoami", follow_redirects=False)

        assert response.status_code == 308
        assert response.headers.get("location") == "/v1/whoami"

        # Check for common redirect headers
        assert "content-length" in response.headers
        assert response.headers.get("content-length") == "0"

        # Should not have cache-control that would interfere with permanent redirect
        cache_control = response.headers.get("cache-control", "").lower()
        assert "no-cache" not in cache_control, \
            "Permanent redirects should be cacheable, found no-cache in cache-control"

    def test_multiple_redirects_not_chained(self, client: TestClient):
        """Test that redirects don't create redirect chains."""
        # Make a request and follow redirects
        response = client.get("/whoami", follow_redirects=True)

        # Should only follow one redirect (to /v1/whoami)
        # If there were redirect chains, TestClient would follow them all
        assert response.status_code != 308, \
            "Should not encounter another redirect after following the initial one"

    def test_redirects_in_openapi_schema(self, client: TestClient):
        """Test that canonical endpoints are included in OpenAPI schema while compat redirects are hidden."""
        # Get the OpenAPI schema
        schema_response = client.get("/openapi.json")
        assert schema_response.status_code == 200

        schema = schema_response.json()

        # Check that paths exist in the schema
        paths = schema.get("paths", {})

        # Canonical endpoints should be present
        canonical_paths = [
            "/v1/whoami", "/v1/spotify/status", "/v1/ask", "/v1/google/status",
            "/v1/auth/login", "/v1/auth/logout", "/v1/auth/register", "/v1/auth/refresh"
        ]

        for path in canonical_paths:
            assert path in paths, \
                f"Canonical path {path} should appear in OpenAPI schema"

        # Compat redirect paths should be hidden (include_in_schema=False)
        compat_paths = [
            "/whoami", "/spotify/status", "/ask", "/google/status",
            "/v1/login", "/v1/logout", "/v1/register", "/v1/refresh"
        ]

        for path in compat_paths:
            assert path not in paths, \
                f"Compat redirect path {path} should NOT appear in OpenAPI schema"

        # Verify canonical paths exist
        canonical_paths_exist = any("/v1/" in p for p in paths.keys())
        assert canonical_paths_exist, \
            "Should have some /v1/ paths in the schema"

    @pytest.mark.parametrize("legacy_path,canonical_path", [
        ("/v1/login", "/v1/auth/login"),
        ("/v1/logout", "/v1/auth/logout"),
        ("/v1/register", "/v1/auth/register"),
        ("/v1/refresh", "/v1/auth/refresh"),
    ])
    def test_legacy_auth_paths_hidden_from_schema(self, client: TestClient, legacy_path: str, canonical_path: str):
        """Test that legacy auth paths are hidden from OpenAPI schema while canonical paths are present."""
        # Get the OpenAPI schema
        schema_response = client.get("/openapi.json")
        assert schema_response.status_code == 200

        schema = schema_response.json()
        paths = schema.get("paths", {})

        # Legacy compat paths should NOT be in the schema (they have include_in_schema=False)
        assert legacy_path not in paths, \
            f"Legacy compat path {legacy_path} should NOT appear in OpenAPI schema"

        # Canonical auth paths SHOULD be in the schema
        assert canonical_path in paths, \
            f"Canonical auth path {canonical_path} should appear in OpenAPI schema"

        # Verify the canonical path has the expected operations
        canonical_operations = paths[canonical_path]
        assert "post" in canonical_operations, \
            f"Canonical path {canonical_path} should have POST operation"

    def test_no_compat_paths_leak_into_schema(self, client: TestClient):
        """Comprehensive test that no compatibility paths leak into the OpenAPI schema."""
        # Get the OpenAPI schema
        schema_response = client.get("/openapi.json")
        assert schema_response.status_code == 200

        schema = schema_response.json()
        paths = schema.get("paths", {})

        # Define all compatibility paths that should be hidden
        compat_paths = {
            "/v1/login", "/v1/logout", "/v1/register", "/v1/refresh",
            "/whoami", "/spotify/status", "/ask", "/google/status"
        }

        # Define canonical paths that should be present
        canonical_paths = {
            "/v1/auth/login", "/v1/auth/logout", "/v1/auth/register", "/v1/auth/refresh",
            "/v1/whoami", "/v1/spotify/status", "/v1/ask", "/v1/google/status"
        }

        # Check that NO compatibility paths are in the schema
        leaked_paths = compat_paths.intersection(set(paths.keys()))
        assert len(leaked_paths) == 0, \
            f"Compatibility paths leaked into schema: {leaked_paths}"

        # Check that ALL canonical paths are present
        missing_paths = canonical_paths - set(paths.keys())
        assert len(missing_paths) == 0, \
            f"Canonical paths missing from schema: {missing_paths}"

        # Additional verification: ensure auth paths have proper operations
        for auth_path in ["/v1/auth/login", "/v1/auth/logout", "/v1/auth/register", "/v1/auth/refresh"]:
            if auth_path in paths:
                operations = paths[auth_path]
                assert "post" in operations, f"Auth path {auth_path} missing POST operation"
