from fastapi.routing import APIRoute


def test_no_duplicate_auth_routes():
    """Ensure no duplicate handlers for the same HTTP method on auth routes."""

    from app.main import app

    # Group routes by path and method combination
    path_method_handlers = {}
    for route in app.routes:
        if isinstance(route, APIRoute):
            for method in route.methods or []:
                key = (route.path, method)
                path_method_handlers.setdefault(key, []).append(route)

    # Check that each (path, method) combination has exactly one handler
    for (path, method), handlers in path_method_handlers.items():
        if path.startswith("/v1/auth/") or path in ["/v1/whoami", "/v1/csrf"]:
            assert (
                len(handlers) == 1
            ), f"Duplicate handlers for {method} {path}: {[h.endpoint for h in handlers]}"

    # Get all actual auth routes that exist
    actual_auth_routes = [
        path
        for (path, method) in path_method_handlers.keys()
        if path.startswith("/v1/auth/") or path in ["/v1/whoami", "/v1/csrf"]
    ]

    # Specifically check the routes we care about (only if they exist)
    auth_routes_to_check = [
        "/v1/whoami",
        "/v1/auth/login",
        "/v1/auth/logout",
        "/v1/auth/logout_all",
        "/v1/auth/refresh",
        "/v1/auth/token",
        "/v1/auth/google/callback",  # Has both GET and POST - that's OK
        "/v1/auth/clerk/finish",
        "/v1/auth/dev/login",
        "/v1/auth/dev/token",
        "/v1/auth/examples",
        "/v1/auth/finish",
        "/v1/csrf",
    ]

    for path in auth_routes_to_check:
        if path in actual_auth_routes:
            # Get all methods for this path
            path_methods = [
                method for (p, method) in path_method_handlers.keys() if p == path
            ]

            # Ensure no duplicate handlers for the same method
            for method in path_methods:
                handlers = path_method_handlers[(path, method)]
                assert (
                    len(handlers) == 1
                ), f"Duplicate {method} handlers for {path}: {[h.endpoint for h in handlers]}"
        else:
            # Skip routes that don't exist (they might be conditionally registered)
            print(f"Skipping {path} - route not found in current configuration")


def test_all_routes_have_handlers():
    """Ensure all routes have at least one handler (no orphaned routes)."""

    from app.main import app

    for route in app.routes:
        if isinstance(route, APIRoute):
            assert (
                route.endpoint is not None
            ), f"Route {route.path} has no endpoint handler"
            assert callable(
                route.endpoint
            ), f"Route {route.path} endpoint is not callable"
