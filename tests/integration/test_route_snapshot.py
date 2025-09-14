"""Public route snapshot test - regression tripwire for critical routes."""

import importlib


def test_public_route_snapshot():
    """Ensure critical public routes are present and haven't been accidentally removed."""
    app = importlib.import_module("app.main").create_app()

    # Get all routes with HTTP methods (excluding WebSocket routes, mounts, etc.)
    got = sorted({r.path for r in app.routes if hasattr(r, "methods")})

    # Critical public routes that should always be available
    expected = sorted(
        [
            "/health",
            "/healthz",
            "/healthz/live",
            "/healthz/deps",
            "/health/vector_store",
            "/v1/health",
            "/v1/health/vector_store",
            "/v1/ping",
            "/v1/vendor-health",
        ]
    )

    for p in expected:
        assert p in got, f"Missing critical public route: {p}"

    # Ensure we have at least some routes (sanity check)
    assert len(got) > 10, f"Expected many routes, got: {got}"
