import os
from fastapi.testclient import TestClient


def _setup_app(monkeypatch):
    os.environ.setdefault("OLLAMA_URL", "http://x")
    os.environ.setdefault("OLLAMA_MODEL", "llama3")
    os.environ.setdefault("HOME_ASSISTANT_URL", "http://ha")
    os.environ.setdefault("HOME_ASSISTANT_TOKEN", "token")
    # Enable per-request env reload for config endpoint smoke
    os.environ.setdefault("ENV_RELOAD_ON_REQUEST", "1")
    from app import main
    monkeypatch.setattr(main, "ha_startup", lambda: None)
    monkeypatch.setattr(main, "llama_startup", lambda: None)
    return main.app


def test_health_and_headers(monkeypatch):
    app = _setup_app(monkeypatch)
    c = TestClient(app)
    r = c.get("/v1/healthz")
    assert r.status_code == 200
    # Core observability headers present
    assert r.headers.get("X-Request-ID")
    assert r.headers.get("X-RateLimit-Limit") is not None
    # Basic security headers present (CSP, nosniff)
    assert "Content-Security-Policy" in r.headers
    assert r.headers.get("X-Content-Type-Options") == "nosniff"


def test_rate_limit_status(monkeypatch):
    app = _setup_app(monkeypatch)
    c = TestClient(app)
    r = c.get("/v1/rate_limit_status")
    assert r.status_code == 200
    data = r.json()
    assert "backend" in data and "limits" in data


