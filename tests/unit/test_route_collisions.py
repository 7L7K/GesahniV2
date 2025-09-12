import pytest

from app.main import create_app


def test_no_route_collisions():
    """Importing and creating the app should raise no ValueError for duplicate routes."""
    # create_app will run the route-collision check during composition
    try:
        _ = create_app()
    except ValueError as e:
        pytest.fail(f"Route collisions detected during app creation: {e}")

import pytest


def test_no_route_collisions():
    """Import the app to trigger startup checks and ensure there are no duplicate
    (method, path) registrations. If duplicates exist, app import/startup should
    raise a ValueError and fail this test.
    """
    # Import happens at module level in app.main; this will run create_app()
    from app import app as _app

    # Basic sanity: ensure app has routes and the startup check passed
    routes = getattr(_app, "routes", None)
    assert routes is not None and len(routes) > 0


