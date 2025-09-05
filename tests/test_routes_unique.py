from app.main import create_app


def test_no_path_method_collisions():
    """Test that no routes have conflicting (path, method) combinations."""
    app = create_app()
    seen = {}
    dupes = []

    for route in app.routes:
        # Handle both APIRoute and other route types
        if hasattr(route, 'methods') and hasattr(route, 'path'):
            methods = route.methods or []
            path = route.path
            endpoint_name = getattr(route.endpoint, "__name__", "?") if hasattr(route, 'endpoint') else "?"

            for method in methods:
                key = (path, method)
                if key in seen:
                    dupes.append((key, seen[key], endpoint_name))
                else:
                    seen[key] = endpoint_name

    assert not dupes, f"Colliding routes found: {dupes}"