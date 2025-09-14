import importlib
from collections import Counter

from fastapi.testclient import TestClient


def _paths(app):
    return [getattr(r, "path", None) for r in app.routes if getattr(r, "path", None)]


def test_no_duplicate_root_health():
    m = importlib.import_module("app.main")
    app = m.create_app()
    counts = Counter(_paths(app))
    for p in ["/health", "/healthz"]:
        assert counts[p] == 1, f"Duplicate route detected for {p}: {counts[p]}"


def test_health_routes_work():
    m = importlib.import_module("app.main")
    app = m.create_app()
    c = TestClient(app)
    assert c.get("/health").status_code < 400
    assert c.get("/healthz").status_code < 400
    assert c.get("/healthz/live").status_code < 400
