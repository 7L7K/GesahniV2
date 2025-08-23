from http import HTTPStatus

from fastapi.testclient import TestClient

from app.main import app


def test_csrf_missing_cookie(monkeypatch):
    monkeypatch.setenv("CSRF_ENABLED", "1")
    monkeypatch.setenv("CSRF_LEGACY_GRACE", "0")
    c = TestClient(app)
    # Send header only; no cookie
    r = c.post("/v1/profile", headers={"X-CSRF-Token": "tok"})
    assert r.status_code == HTTPStatus.FORBIDDEN


