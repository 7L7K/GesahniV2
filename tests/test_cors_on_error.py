# tests/test_cors_on_error.py
import importlib

from starlette.testclient import TestClient


def test_cors_on_error_has_headers(monkeypatch):
    monkeypatch.setenv("ENV", "dev")
    monkeypatch.setenv("DEV_MODE", "1")
    if "app.main" in importlib.sys.modules:
        del importlib.sys.modules["app.main"]
    from app.main import app

    client = TestClient(app)
    # hit any route that triggers a 500 via EnhancedErrorHandling
    resp = client.get(
        "/__definitely_missing__", headers={"Origin": "http://localhost:3000"}
    )
    # Even for 404/500, should have CORS header
    # Origin must be in your allow_origins; use the canonical dev origin
    assert "access-control-allow-origin" in {
        k.lower(): v for k, v in resp.headers.items()
    }
