from http import HTTPStatus

from fastapi.testclient import TestClient

from app.main import app


def test_csrf_enabled_globally(monkeypatch):
    monkeypatch.setenv("CSRF_ENABLED", "1")
    monkeypatch.setenv("CSRF_LEGACY_GRACE", "0")
    c = TestClient(app)
    # POST without cookie/header should be blocked
    r = c.post("/v1/profile")
    assert r.status_code in {HTTPStatus.FORBIDDEN, HTTPStatus.BAD_REQUEST}
    # Now provide both cookie + header
    c.cookies.set("csrf_token", "tok")
    r2 = c.post("/v1/profile", headers={"X-CSRF-Token": "tok"}, json={})
    assert r2.status_code == HTTPStatus.OK


