"""
Test for duplicate route detection to prevent route collisions.
"""

import os

from fastapi.routing import APIRoute, APIWebSocketRoute, Mount
from fastapi.testclient import TestClient

from app.main import create_app


def test_no_duplicate_routes():
    """
    Test that no duplicate routes are registered in the application.

    This test ensures that route collisions are caught early in development
    and prevents issues like the legacy /v1/state vs system /v1/state collision.
    """
    app = create_app()
    seen_routes = {}
    duplicates = []

    def get_route_key(route):
        """Get a unique key for route collision detection"""
        if isinstance(route, APIRoute):
            methods = ",".join(sorted(route.methods or []))
            return f"HTTP:{methods}:{route.path}"
        elif isinstance(route, APIWebSocketRoute):
            return f"WS:{route.path}"
        elif isinstance(route, Mount):
            return f"MOUNT:{route.path}:{route.app}"
        else:
            return f"OTHER:{type(route).__name__}:{getattr(route, 'path', str(route))}"

    def get_endpoint_info(route):
        """Get endpoint information for route"""
        if isinstance(route, APIRoute | APIWebSocketRoute):
            if hasattr(route.endpoint, "__module__") and hasattr(
                route.endpoint, "__name__"
            ):
                return f"{route.endpoint.__module__}.{route.endpoint.__name__}"
            else:
                return str(route.endpoint)
        elif isinstance(route, Mount):
            return f"Mount:{route.app}"
        else:
            return str(route)

    for route in app.router.routes:
        key = get_route_key(route)
        endpoint_info = get_endpoint_info(route)

        if key in seen_routes:
            duplicates.append((key, seen_routes[key], endpoint_info))
        else:
            seen_routes[key] = endpoint_info

    # Provide detailed error message if duplicates found
    if duplicates:
        error_msg = "Duplicate routes detected:\n"
        for key, existing_endpoint, new_endpoint in duplicates:
            error_msg += f"  Route: {key}\n"
            error_msg += f"    Existing: {existing_endpoint}\n"
            error_msg += f"    Duplicate: {new_endpoint}\n"
        raise AssertionError(error_msg)

    # Ensure we have a reasonable number of routes (sanity check)
    assert len(seen_routes) > 10, f"Expected > 10 routes, got {len(seen_routes)}"


def test_legacy_routes_not_present_by_default():
    """
    Test that legacy routes are not present by default (LEGACY_MUSIC_HTTP=0).

    This test verifies that the environment gating works correctly.
    """

    # Ensure LEGACY_MUSIC_HTTP is not set or is 0
    legacy_env = os.getenv("LEGACY_MUSIC_HTTP", "0")
    assert legacy_env == "0", f"Expected LEGACY_MUSIC_HTTP=0 for test, got {legacy_env}"

    app = create_app()

    # Check that legacy music HTTP routes are not present
    legacy_paths = ["/v1/state"]  # This should now be handled by system_router only

    found_legacy_routes = []
    for route in app.router.routes:
        if isinstance(route, APIRoute):
            if route.path in legacy_paths:
                found_legacy_routes.append(route.path)

    # Should only find system routes, not legacy redirect routes
    assert (
        len(found_legacy_routes) <= 1
    ), f"Found unexpected legacy routes: {found_legacy_routes}"


def test_legacy_routes_present_when_enabled():
    """
    Test that legacy routes are present when LEGACY_MUSIC_HTTP=1.

    This test verifies that the environment gating works correctly when enabled.
    """

    # Temporarily set the environment variable
    original_value = os.environ.get("LEGACY_MUSIC_HTTP")
    os.environ["LEGACY_MUSIC_HTTP"] = "1"

    try:
        app = create_app()

        # Check that legacy routes are present
        legacy_redirect_found = False
        for route in app.router.routes:
            if isinstance(route, APIRoute):
                if "/legacy/state" in route.path:
                    legacy_redirect_found = True
                    break

        assert (
            legacy_redirect_found
        ), "Legacy redirect route /v1/legacy/state not found when LEGACY_MUSIC_HTTP=1"

    finally:
        # Restore original environment
        if original_value is None:
            os.environ.pop("LEGACY_MUSIC_HTTP", None)
        else:
            os.environ["LEGACY_MUSIC_HTTP"] = original_value


def _paths(client):
    """
    Extract path->methods mapping from OpenAPI schema.

    Returns a dictionary mapping paths to sets of lowercase HTTP methods.
    """
    openapi_data = client.get("/openapi.json").json()
    paths_data = openapi_data.get("paths", {})

    out = {}
    for path, methods in paths_data.items():
        out[path] = {m.lower() for m in methods.keys()}
    return out


def test_default_routes_no_legacy(monkeypatch):
    """
    Test that default routes (LEGACY_MUSIC_HTTP=0) do not include legacy endpoints.

    This ensures that the legacy /v1/legacy/state endpoint is not exposed
    when legacy music HTTP support is disabled (the default).
    """
    monkeypatch.setenv("LEGACY_MUSIC_HTTP", "0")

    # Create a fresh app instance with the environment variable set
    app = create_app()
    client = TestClient(app)
    paths = _paths(client)

    # Legacy endpoint should NOT be present
    assert (
        "/v1/legacy/state" not in paths
    ), "Legacy /v1/legacy/state should not be present when LEGACY_MUSIC_HTTP=0"

    # But the canonical system state endpoint should be present
    assert (
        "/v1/state" in paths and "get" in paths["/v1/state"]
    ), "/v1/state GET should be available"


def test_legacy_enabled_has_redirect(monkeypatch):
    """
    Test that legacy routes are present and functional when LEGACY_MUSIC_HTTP=1.

    This ensures that the legacy /v1/legacy/state endpoint is exposed and properly
    redirects to the canonical endpoint when legacy music HTTP support is enabled.
    """
    monkeypatch.setenv("LEGACY_MUSIC_HTTP", "1")

    # Create a fresh app instance with the environment variable set
    app = create_app()
    client = TestClient(app)

    # Test that the legacy endpoint is present in OpenAPI
    paths = _paths(client)
    assert (
        "/v1/legacy/state" in paths and "get" in paths["/v1/legacy/state"]
    ), "/v1/legacy/state GET should be available when LEGACY_MUSIC_HTTP=1"

    # Test the actual redirect behavior (307 status code)
    response = client.get("/v1/legacy/state", allow_redirects=False)
    assert (
        response.status_code == 307
    ), f"Expected 307 redirect, got {response.status_code}"

    # Check that redirect location points to a valid canonical endpoint
    location = response.headers.get("location")
    valid_targets = {"/v1/music/state", "/v1/state", "/v1/system/state"}
    assert (
        location in valid_targets
    ), f"Redirect location {location} should be one of {valid_targets}"
