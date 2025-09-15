from app.main import create_app


def test_critical_endpoints_exist():
    """Test that critical endpoints are properly registered."""
    app = create_app()
    routes = [r.path for r in app.routes if hasattr(r, "path")]

    # These are the critical endpoints we care about
    critical_endpoints = ["/v1/whoami", "/v1/me", "/health"]

    for endpoint in critical_endpoints:
        assert endpoint in routes, f"Critical endpoint {endpoint} not found in routes"


def test_no_duplicate_critical_endpoints():
    """Test that critical endpoints don't have problematic duplicates."""
    app = create_app()
    routes = [
        (r.path, tuple(r.methods or []))
        for r in app.routes
        if hasattr(r, "path") and hasattr(r, "methods")
    ]

    critical_endpoints = ["/v1/whoami", "/v1/me", "/health"]

    for endpoint in critical_endpoints:
        # Find routes for this path
        endpoint_routes = [
            (path, methods) for path, methods in routes if path == endpoint
        ]
        # Group by HTTP method (excluding OPTIONS which FastAPI adds automatically)
        method_counts = {}
        for _path, methods in endpoint_routes:
            for method in methods:
                if (
                    method != "OPTIONS"
                ):  # OPTIONS are auto-generated and expected to be duplicated
                    method_counts[method] = method_counts.get(method, 0) + 1

        # Check that no method has duplicates
        for method, count in method_counts.items():
            assert (
                count == 1
            ), f"Critical endpoint {endpoint} method {method} appears {count} times (should be 1)"


# Soft check for prefix includes - can be expanded when router tracing is available
def test_prefixes_soft_check():
    """Soft check for prefix includes (placeholder for future router tracing)."""
    # This test currently passes but can be enhanced when router tracing
    # is made available in test context
    assert True


def test_router_can_be_created():
    """Test that the app can be created without router errors."""
    try:
        app = create_app()
        # Basic smoke test - app should have routes
        assert len(app.routes) > 0
    except Exception as e:
        raise AssertionError(f"App creation failed: {e}")
