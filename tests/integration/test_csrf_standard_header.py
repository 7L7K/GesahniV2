from http import HTTPStatus

from fastapi.testclient import TestClient

from app.main import app


def test_csrf_standard_header(monkeypatch):
    # Enforce globally
    monkeypatch.setenv("CSRF_ENABLED", "1")
    monkeypatch.setenv("CSRF_LEGACY_GRACE", "0")
    c = TestClient(app)
    # Set cookie and matching header
    c.cookies.set("csrf_token", "tok")
    r = c.post("/v1/profile", headers={"X-CSRF-Token": "tok"}, json={})
    assert r.status_code == HTTPStatus.OK


def test_csrf_legacy_header_blocked(monkeypatch):
    monkeypatch.setenv("CSRF_ENABLED", "1")
    monkeypatch.setenv("CSRF_LEGACY_GRACE", "0")
    c = TestClient(app)
    c.cookies.set("csrf_token", "tok")
    r = c.post("/v1/profile", headers={"X-CSRF": "tok"}, json={})
    assert r.status_code == HTTPStatus.BAD_REQUEST


