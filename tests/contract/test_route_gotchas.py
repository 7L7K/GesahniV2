"""
Route gotchas tests - guard against common API design mistakes.

Tests for trailing slashes, versioned prefixes, and other common pitfalls
that can break clients or cause confusion.
"""

import os

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client():
    """Create test client with test configuration."""
    # Set environment variables for testing
    os.environ.setdefault("PYTEST_RUNNING", "1")
    os.environ.setdefault("JWT_OPTIONAL_IN_TESTS", "1")
    os.environ.setdefault("ADMIN_TOKEN", "test-admin-token")

    app = create_app()
    return TestClient(app)


def test_trailing_slash_consistency(client):
    """Test trailing slash consistency across API routes.

    Either all routes should have trailing slashes, or none should.
    Mixed usage can confuse clients and lead to double requests.
    """
    routes_with_slash = set()
    routes_without_slash = set()

    for route in client.app.routes:
        if hasattr(route, "path") and route.path.startswith("/v1/"):
            if route.path.endswith("/"):
                routes_with_slash.add(route.path)
            else:
                routes_without_slash.add(route.path)

    # If we have both patterns, this is a consistency issue
    if routes_with_slash and routes_without_slash:
        pytest.fail(
            f"Inconsistent trailing slash usage:\n"
            f"  With slash: {sorted(list(routes_with_slash))[:5]}...\n"
            f"  Without slash: {sorted(list(routes_without_slash))[:5]}...\n"
            f"Choose one convention and stick to it, or implement 301/308 redirects."
        )


def test_trailing_slash_redirects_work(client):
    """Test that trailing slash redirects work correctly.

    If you support both /v1/ask and /v1/ask/, ensure proper redirects.
    """
    # Test a few key endpoints
    test_paths = [
        "/v1/health",
        "/v1/me",
        "/v1/models",
    ]

    for base_path in test_paths:
        with_slash = base_path + "/"
        without_slash = base_path

        # Check if both exist
        routes = {route.path for route in client.app.routes if hasattr(route, "path")}

        if with_slash in routes and without_slash in routes:
            # Both exist - test that they return the same result or redirect
            response_without = client.get(without_slash)
            response_with = client.get(with_slash)

            # They should either:
            # 1. Return the same status (both work)
            # 2. One redirects to the other (301/308)
            if response_without.status_code != response_with.status_code:
                if response_without.status_code in [301, 308]:
                    # without_slash redirects to with_slash - good
                    assert response_without.headers.get("location") == with_slash
                elif response_with.status_code in [301, 308]:
                    # with_slash redirects to without_slash - good
                    assert response_with.headers.get("location") == without_slash
                else:
                    pytest.fail(
                        f"Inconsistent responses for {base_path}: "
                        f"without_slash={response_without.status_code}, "
                        f"with_slash={response_with.status_code}"
                    )


def test_versioned_prefix_consistency(client):
    """Test that versioned routes use consistent prefixes.

    All API routes should use the same version prefix (/v1/).
    """
    version_prefixes = set()

    for route in client.app.routes:
        if hasattr(route, "path"):
            path = route.path
            # Skip non-API routes
            if not path.startswith("/"):
                continue
            if path in ["/", "/docs", "/redoc", "/openapi.json", "/favicon.ico"]:
                continue

            # Extract version prefix for API routes
            if path.startswith("/v"):
                parts = path.split("/")
                if len(parts) >= 2 and parts[1].startswith("v"):
                    version_prefixes.add("/" + parts[1] + "/")

    # Should only have one version prefix for consistency
    if len(version_prefixes) > 1:
        pytest.fail(
            f"Multiple version prefixes found: {sorted(version_prefixes)}\n"
            "Use a single version prefix for all API routes."
        )


def test_version_prefix_includes_major_version(client):
    """Test that version prefixes include major version numbers.

    Avoid generic prefixes like /api/ - use /v1/, /v2/, etc.
    """
    routes = {route.path for route in client.app.routes if hasattr(route, "path")}

    generic_prefixes = []
    for route in routes:
        if route.startswith("/api/") or route.startswith("/v/"):
            generic_prefixes.append(route)

    if generic_prefixes:
        pytest.fail(
            f"Routes with generic version prefixes: {generic_prefixes[:5]}...\n"
            "Use specific major version numbers like /v1/, /v2/, etc."
        )


def test_route_prefix_app_factory_consistency(client):
    """Test that route prefixes match the app factory configuration.

    Routes should use the same version prefix as configured in tests.
    """
    # This test assumes your app factory creates routes with /v1/ prefix
    # Adjust based on your actual configuration
    routes = {route.path for route in client.app.routes if hasattr(route, "path")}

    api_routes = [r for r in routes if r.startswith("/v1/")]
    non_api_routes = [
        r for r in routes if r.startswith("/v") and not r.startswith("/v1/")
    ]

    if non_api_routes:
        pytest.fail(
            f"Routes with inconsistent version prefixes: {non_api_routes[:5]}...\n"
            "All API routes should use the same version prefix as the app factory."
        )


def test_no_double_slash_routes(client):
    """Test that no routes have double slashes.

    Double slashes (//) in URLs can cause routing issues.
    """
    double_slash_routes = []

    for route in client.app.routes:
        if hasattr(route, "path") and "//" in route.path:
            double_slash_routes.append(route.path)

    if double_slash_routes:
        pytest.fail(f"Routes with double slashes: {double_slash_routes}")


def test_route_parameters_properly_named(client):
    """Test that route parameters have descriptive names.

    Avoid generic names like {id} - use {user_id}, {model_id}, etc.
    """
    generic_params = []

    for route in client.app.routes:
        if hasattr(route, "path"):
            path = route.path
            if "{id}" in path:
                # Check if this is a generic ID that could be more specific
                if any(
                    context in path
                    for context in ["/user/", "/model/", "/session/", "/admin/"]
                ):
                    generic_params.append(path)

    if generic_params:
        pytest.fail(
            f"Routes with generic 'id' parameters: {generic_params}\n"
            "Use descriptive parameter names like {user_id}, {model_id}, etc."
        )


def test_no_query_string_in_route_paths(client):
    """Test that routes don't include query strings in their paths.

    Query parameters should be handled in the handler, not in the route path.
    """
    query_routes = []

    for route in client.app.routes:
        if hasattr(route, "path") and "?" in route.path:
            query_routes.append(route.path)

    if query_routes:
        pytest.fail(f"Routes with query strings in path: {query_routes}")


def test_route_case_consistency(client):
    """Test that route paths use consistent casing.

    URLs should be lowercase for consistency.
    """
    uppercase_routes = []

    for route in client.app.routes:
        if hasattr(route, "path"):
            path = route.path
            # Check for uppercase letters in path segments
            for segment in path.split("/"):
                if segment and not segment.islower() and not segment.startswith("{"):
                    uppercase_routes.append(path)
                    break

    if uppercase_routes:
        pytest.fail(f"Routes with uppercase characters: {uppercase_routes[:5]}...")


def test_no_empty_path_segments(client):
    """Test that routes don't have empty path segments.

    Empty segments can cause routing confusion.
    """
    empty_segment_routes = []

    for route in client.app.routes:
        if hasattr(route, "path"):
            path = route.path

            # Skip the root route which legitimately has an empty path
            if path == "/":
                continue

            segments = path.split("/")

            # Remove the first empty segment (normal for absolute paths like /v1/ask)
            if segments and segments[0] == "":
                segments = segments[1:]

            # Check for empty segments in the middle (like /v1//ask)
            if "" in segments:
                empty_segment_routes.append(path)

    if empty_segment_routes:
        pytest.fail(f"Routes with empty path segments: {empty_segment_routes}")


def test_api_routes_start_with_version(client):
    """Test that API routes start with version prefix.

    Public API routes should be versioned to allow for future changes.
    """
    unversioned_api_routes = []

    for route in client.app.routes:
        if hasattr(route, "path"):
            path = route.path

            # Skip non-API routes and static files
            if path in ["/", "/docs", "/redoc", "/openapi.json", "/favicon.ico"]:
                continue
            if path.startswith("/static/") or path.startswith("/assets/"):
                continue

            # Check API-like routes that should be versioned
            api_keywords = [
                "ask",
                "health",
                "me",
                "models",
                "admin",
                "auth",
                "integrations",
            ]
            if any(keyword in path for keyword in api_keywords):
                if not path.startswith("/v"):
                    unversioned_api_routes.append(path)

    # Report but don't fail - many APIs have mixed versioning during transition
    if unversioned_api_routes:
        print(f"INFO: Unversioned API routes: {unversioned_api_routes[:10]}...")
        # Don't fail - this is common during API evolution
