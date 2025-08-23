from fastapi.routing import APIRoute


def test_no_duplicate_core_routes():
    from app.main import app

    paths = {}
    for r in app.routes:
        if isinstance(r, APIRoute):
            key = (tuple(sorted(r.methods or [])), r.path)
            paths.setdefault(key, []).append(r)
    # Ensure single handler for these canonical routes
    for methods, path in [
        (("GET",), "/v1/whoami"),
        (("GET",), "/v1/sessions"),
        (("POST",), "/v1/auth/logout"),
        (("POST",), "/v1/auth/refresh"),
    ]:
        key = (methods, path)
        matches = [
            rt
            for k, v in paths.items()
            if k[1] == path and methods[0] in k[0]
            for rt in v
        ]
        assert len(matches) == 1, f"duplicate handler for {methods} {path}: {matches}"
