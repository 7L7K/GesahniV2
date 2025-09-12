"""Unit tests to ensure compatibility redirect routes are hidden from OpenAPI schema.

These tests verify that legacy compatibility endpoints (redirects) do not appear
in the OpenAPI schema, maintaining a clean API surface for consumers.
"""
from __future__ import annotations

import pytest
from fastapi.openapi.utils import get_openapi

from app.main import create_app


class TestCompatRoutesHidden:
    """Test that compatibility routes are properly hidden from OpenAPI schema."""

    @pytest.fixture
    def openapi_schema(self):
        """Generate OpenAPI schema for testing."""
        app = create_app()
        return get_openapi(
            title=app.title,
            version=app.version,
            openapi_version=app.openapi_version,
            description=app.description,
            routes=app.routes,
        )

    def test_no_hidden_categories_in_schema(self, openapi_schema):
        """Test that hidden categories (compat, debug, callbacks, mocks) do not appear in OpenAPI schema."""
        paths = openapi_schema.get("paths", {})

        # Hidden categories that should NOT be in schema
        hidden_patterns = [
            # Compat routes
            "/whoami",
            "/health",
            "/healthz",
            "/status",
            "/spotify/status",
            "/ask",
            "/google/status",
            "/v1/login",
            "/v1/logout",
            "/v1/register",
            "/v1/refresh",
            "/v1/auth/google/callback",
            "/google/oauth/callback",
            # Debug routes
            "/v1/debug/config",
            "/v1/debug/token-health",
            "/docs/ws",
            "/v1/debug/oauth/routes",
            "/v1/debug/oauth/config",
            "/_diag/auth",
            "/v1/debug/oauth",
            # Util routes (most are CORS preflight OPTIONS, ping, csrf)
            "/csrf",
            "/ping",
            # Callback routes (already covered above, but explicit)
            "/v1/google/callback",
            "/v1/spotify/callback",
            "/v1/spotify/callback-test",
            # Mock routes
            "/mock/set_access_cookie",
        ]

        # Check that none of the hidden patterns appear in the schema
        for pattern in hidden_patterns:
            assert pattern not in paths, f"Hidden route '{pattern}' should not be in OpenAPI schema"

    def test_no_legacy_admin_paths_in_schema(self, openapi_schema):
        """Test that legacy /admin/* paths are not in OpenAPI schema."""
        paths = openapi_schema.get("paths", {})

        # Check for legacy admin paths that should redirect
        legacy_admin_patterns = [
            "/admin/ping",
            "/admin/config",
            "/admin/flags",
            "/admin/metrics",
            "/admin/system/status",
            "/admin/errors",
            "/admin/router/decisions",
            "/admin/tokens/google",
            "/admin/rbac/info",
            "/admin/users/me",
            "/admin/retrieval/last",
            "/admin/backup",
        ]

        for pattern in legacy_admin_patterns:
            assert pattern not in paths, f"Legacy admin route '{pattern}' should not be in OpenAPI schema"

    def test_no_legacy_spotify_integration_paths_in_schema(self, openapi_schema):
        """Test that legacy /v1/integrations/spotify/* paths are not in OpenAPI schema."""
        paths = openapi_schema.get("paths", {})

        # Check for legacy Spotify integration paths that should redirect
        legacy_spotify_patterns = [
            "/v1/integrations/spotify/status",
            "/v1/integrations/spotify/connect",
            "/v1/integrations/spotify/callback",
            "/v1/integrations/spotify/disconnect",
        ]

        for pattern in legacy_spotify_patterns:
            assert pattern not in paths, f"Legacy Spotify integration route '{pattern}' should not be in OpenAPI schema"

    def test_canonical_categories_present_in_schema(self, openapi_schema):
        """Test that canonical API categories are present in the schema."""
        paths = openapi_schema.get("paths", {})

        # Canonical categories that should be present in the schema
        # Focus on core categories that are always expected to be present
        canonical_categories = {
            "Auth": [
                "/v1/auth/login",
                "/v1/auth/logout",
                "/v1/auth/register",
                "/v1/auth/refresh",
                "/v1/auth/token",
                "/v1/google/login_url",
            ],
            "Admin": [
                "/v1/admin/ping",
                "/v1/admin/config",
                "/v1/admin/flags",
                "/v1/admin/metrics",
            ],
            "Music": [
                "/v1/music",
                "/v1/spotify/status",
                "/v1/spotify/connect",
                "/v1/spotify/disconnect",
            ],
            "Care": [
                "/v1/care/alerts",
                "/v1/ask",
            ],
            "Health/Status": [
                "/v1/health",
                "/v1/healthz",
                "/v1/status",
            ],
            "User/Profile": [
                "/v1/me",
            ],
        }

        # Check that canonical paths are present
        for category, category_paths in canonical_categories.items():
            present_count = 0
            for path in category_paths:
                if path in paths:
                    present_count += 1

            # Assert that at least some paths from each category are present
            # These are core categories that should always be present
            assert present_count > 0, f"Category '{category}' should have at least some paths present in schema, found {present_count}/{len(category_paths)}"

    def test_hidden_routers_not_exposed_in_schema(self, openapi_schema):
        """Test that routers with include_in_schema=False do not expose their routes."""
        paths = openapi_schema.get("paths", {})

        # All routes from routers that should be hidden
        hidden_router_patterns = [
            # From compat_api.py (include_in_schema=False)
            "/whoami", "/health", "/status", "/spotify/status",
            "/ask", "/google/status", "/v1/login", "/v1/logout", "/v1/register",
            "/v1/refresh", "/v1/auth/google/callback", "/google/oauth/callback",
            "/v1/integrations/spotify/status", "/v1/integrations/spotify/connect",
            "/v1/integrations/spotify/callback", "/v1/integrations/spotify/disconnect",

            # From debug.py (include_in_schema=False)
            "/v1/debug/config", "/v1/debug/token-health", "/docs/ws",
            "/v1/debug/oauth/routes", "/v1/debug/oauth/config", "/_diag/auth",
            "/v1/debug/oauth",

            # From util.py (include_in_schema=False)
            "/csrf", "/ping",

            # From various routers with include_in_schema=False (callbacks, mocks, etc.)
            "/v1/google/callback", "/v1/spotify/callback", "/v1/spotify/callback-test",
            "/mock/set_access_cookie",
        ]

        hidden_exposed_count = 0
        exposed_hidden_paths = []
        for path in paths:
            for hidden_pattern in hidden_router_patterns:
                if hidden_pattern == path or (path.startswith(hidden_pattern + "/") and hidden_pattern != "/"):
                    hidden_exposed_count += 1
                    exposed_hidden_paths.append(path)
                    break

        assert hidden_exposed_count == 0, f"Found {hidden_exposed_count} routes from hidden routers exposed in schema: {exposed_hidden_paths}"
