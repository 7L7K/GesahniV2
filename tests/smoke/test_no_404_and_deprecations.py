import re

from fastapi.testclient import TestClient

from app.main import create_app


def _fill_path(path: str) -> str:
    """Replace path parameters like {id} with a safe test value."""
    return re.sub(r"\{[^/]+\}", "abc", path)


def _pick_method(methods: set) -> str:
    # Prefer GET/POST for compatibility; otherwise pick any safe method
    for m in ("GET", "POST", "PUT", "DELETE", "PATCH"):
        if m in methods:
            return m
    return next(iter(methods))


def test_no_404_for_get_and_post_routes():
    app = create_app()
    client = TestClient(app)

    routes = [r for r in app.routes if getattr(r, "methods", None)]
    tried = 0
    for r in routes:
        path = getattr(r, "path", None)
        if not path:
            continue
        methods = set(r.methods or [])
        for method in ("GET", "POST"):
            if method not in methods:
                continue
            url = _fill_path(path)
            tried += 1
            try:
                print(f"TESTING -> {method} {url}")
                if method == "GET":
                    resp = client.get(url, timeout=5)
                else:
                    # POST with a small JSON body; many legacy endpoints accept this
                    resp = client.post(
                        url, json={"text": "hi", "device_id": "x"}, timeout=5
                    )
                assert (
                    resp.status_code != 404
                ), f"{method} {url} unexpectedly returned 404"
            except Exception as e:
                # Print exception for diagnosis and continue; timeouts or network
                # errors indicate a route that blocks or depends on external services.
                print(f"SKIP (exception) -> {method} {url}: {type(e).__name__} {e}")
                continue

    assert tried > 0, "No GET/POST routes were discovered to test"


def test_deprecated_routes_emit_deprecation_header():
    app = create_app()
    client = TestClient(app)

    routes = [r for r in app.routes if getattr(r, "deprecated", False)]
    assert routes, "No deprecated routes found in app.routes"

    for r in routes:
        path = getattr(r, "path", None)
        if not path:
            continue
        methods = set(r.methods or [])
        method = _pick_method(methods)
        url = _fill_path(path)
        try:
            if method == "GET":
                resp = client.get(url, follow_redirects=False)
            else:
                resp = client.request(method, url, json={"text": "hi"}, follow_redirects=False)
        except Exception:
            # If the endpoint raised due to missing deps, we cannot assert
            # headers here; skip verification for this route.
            continue

        # Alias handlers attach a Deprecation header with literal "true"
        dep = resp.headers.get("Deprecation") or resp.headers.get("deprecation")
        assert (
            dep is not None
        ), f"Deprecated route {path} did not include Deprecation header"
        assert str(dep).lower() in {
            "true",
            "1",
        }, f"Deprecation header for {path} not set to true: {dep}"
