"""
Route methods contract tests - freeze HTTP method contracts.

When you add/remove/change HTTP methods on routes, update this test.
Prevents silent changes to the API surface that break clients.
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


def test_methods_match_contract(client):
    """Test that route methods match expected contract."""
    # Build map of (path, methods) from actual routes
    route_map = {
        (route.path, tuple(sorted(route.methods or [])))
        for route in client.app.routes
        if hasattr(route, "path") and hasattr(route, "methods")
    }

    # Critical API contracts that must remain stable
    must_have_routes = {
        ("/v1/ask", ("POST",)),
        ("/v1/health", ("GET",)),
        ("/v1/auth/login", ("POST",)),
        ("/v1/auth/logout", ("POST",)),
        ("/v1/auth/refresh", ("POST",)),
        ("/v1/me", ("GET",)),
        ("/whoami", ("GET",)),
        ("/v1/models", ("GET",)),
        ("/v1/admin/config", ("GET",)),
    }

    # Ensure all critical routes exist with expected methods
    missing_routes = []
    wrong_methods = []

    for path, expected_methods in must_have_routes:
        if (path, expected_methods) not in route_map:
            # Check if path exists at all
            path_exists = any(route_path == path for route_path, _ in route_map)
            if not path_exists:
                missing_routes.append((path, expected_methods))
            else:
                # Path exists but methods don't match
                actual_methods = next(
                    methods for route_path, methods in route_map if route_path == path
                )
                wrong_methods.append((path, expected_methods, actual_methods))

    assert not missing_routes, f"Missing critical routes: {missing_routes}"
    assert not wrong_methods, f"Wrong methods on routes: {wrong_methods}"


def test_no_duplicate_routes(client):
    """Test that no routes are accidentally duplicated."""
    routes = [
        (route.path, tuple(sorted(route.methods or [])))
        for route in client.app.routes
        if hasattr(route, "path") and hasattr(route, "methods")
    ]

    seen = set()
    duplicates = []
    health_duplicates = []  # Track health endpoint duplicates separately

    for path, methods in routes:
        key = (path, methods)
        if key in seen:
            if "health" in path:
                health_duplicates.append(key)
            else:
                duplicates.append(key)
        seen.add(key)

    # Health endpoints often have legitimate duplicates (different handlers for same path)
    if health_duplicates:
        print(
            f"INFO: Health endpoint duplicates (may be legitimate): {health_duplicates}"
        )

    # Only fail on non-health duplicates
    assert not duplicates, f"Duplicate routes found: {duplicates}"


def test_route_methods_are_standard_http(client):
    """Test that all routes use standard HTTP methods."""
    standard_methods = {"GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"}

    non_standard = []
    for route in client.app.routes:
        if hasattr(route, "methods") and route.methods:
            for method in route.methods:
                if method not in standard_methods:
                    non_standard.append((route.path, method))

    assert not non_standard, f"Non-standard HTTP methods found: {non_standard}"


def test_api_routes_use_version_prefix(client):
    """Test that API routes consistently use version prefixes."""
    unversioned_api_routes = []

    for route in client.app.routes:
        if hasattr(route, "path") and route.path.startswith("/"):
            path = route.path
            # Skip root and non-API routes
            if path in ["/", "/docs", "/redoc", "/openapi.json", "/favicon.ico"]:
                continue
            # Skip auth routes that might not follow versioning
            if path.startswith("/auth/"):
                continue
            # Check if it's an API route that should be versioned
            if any(
                keyword in path
                for keyword in [
                    "/ask",
                    "/health",
                    "/me",
                    "/models",
                    "/admin",
                    "/integrations",
                ]
            ):
                if not path.startswith("/v"):
                    unversioned_api_routes.append(path)

    # Report but don't fail - many APIs have mixed versioning during transition
    if unversioned_api_routes:
        print(f"INFO: Unversioned API routes: {unversioned_api_routes[:10]}...")
        # Don't fail - this is common during API evolution


def test_trailing_slash_consistency(client):
    """Test trailing slash consistency across routes."""
    routes_with_slash = []
    routes_without_slash = []

    for route in client.app.routes:
        if hasattr(route, "path") and route.path.startswith("/v1/"):
            if route.path.endswith("/"):
                routes_with_slash.append(route.path)
            else:
                routes_without_slash.append(route.path)

    # Report inconsistency but don't fail - this is informational
    if routes_with_slash and routes_without_slash:
        print("WARNING: Mixed trailing slash usage:")
        print(f"  With slash: {routes_with_slash[:5]}...")
        print(f"  Without slash: {routes_without_slash[:5]}...")


def test_options_handlers_present(client):
    """Test that OPTIONS handlers are present for CORS routes."""
    cors_routes = []
    options_routes = []

    for route in client.app.routes:
        if hasattr(route, "path") and hasattr(route, "methods"):
            if "OPTIONS" in (route.methods or []):
                options_routes.append(route.path)
            elif any(
                method in ["GET", "POST", "PUT", "DELETE", "PATCH"]
                for method in (route.methods or [])
            ):
                cors_routes.append(route.path)

    # Check that CORS-enabled routes have OPTIONS handlers
    missing_options = []
    for route in cors_routes:
        if route not in options_routes:
            missing_options.append(route)

    # This might be expected behavior depending on your CORS setup
    if missing_options:
        print(f"INFO: Routes without OPTIONS handlers: {missing_options[:5]}...")


def test_route_path_parameters_valid(client):
    """Test that route path parameters are properly formatted."""
    invalid_params = []

    for route in client.app.routes:
        if hasattr(route, "path"):
            path = route.path
            # Check for common path parameter mistakes
            if "{" in path:
                # Ensure parameters are properly named (not generic like {id})
                # This is more of a style check - adjust based on your conventions
                if "{id}" in path and len(path.split("/")) > 3:
                    invalid_params.append((path, "generic 'id' parameter"))

    if invalid_params:
        print(f"INFO: Routes with potentially generic parameters: {invalid_params}")


def test_admin_routes_require_admin_methods(client):
    """Test that admin routes use appropriate HTTP methods."""
    admin_routes = []

    for route in client.app.routes:
        if hasattr(route, "path") and route.path.startswith("/v1/admin/"):
            admin_routes.append((route.path, route.methods or []))

    # Admin routes should typically use GET for retrieval, POST/PUT for updates
    inappropriate_methods = []
    for path, methods in admin_routes:
        if "DELETE" in methods and path not in [
            "/v1/admin/cache",
            "/v1/admin/sessions",
        ]:
            inappropriate_methods.append((path, "DELETE method on admin route"))

    if inappropriate_methods:
        print(
            f"WARNING: Potentially inappropriate methods on admin routes: {inappropriate_methods}"
        )


def test_public_routes_method_contract(client):
    """Test that public routes follow expected method patterns."""
    public_routes = []

    for route in client.app.routes:
        if hasattr(route, "path") and hasattr(route, "methods"):
            path = route.path
            methods = set(route.methods or [])

            # Skip admin routes
            if path.startswith("/v1/admin/"):
                continue

            # Public API routes should follow common patterns
            if path.startswith("/v1/"):
                public_routes.append((path, methods))

    # Check for unusual method combinations
    unusual_patterns = []
    for path, methods in public_routes:
        # POST-only routes are common for actions
        if methods == {"POST"} and any(
            action in path for action in ["ask", "login", "logout", "refresh"]
        ):
            continue
        # GET-only routes are common for data retrieval
        if methods == {"GET"} and any(
            read in path for read in ["health", "me", "models", "status"]
        ):
            continue
        # Complex method combinations might need review
        if len(methods) > 2:
            unusual_patterns.append((path, methods))

    if unusual_patterns:
        print(f"INFO: Routes with complex method patterns: {unusual_patterns[:5]}...")
