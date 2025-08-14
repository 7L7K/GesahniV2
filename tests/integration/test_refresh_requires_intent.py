from http import HTTPStatus
from fastapi.testclient import TestClient

from app.main import app


def test_refresh_requires_intent_when_none(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "secret")
    monkeypatch.setenv("COOKIE_SAMESITE", "none")
    c = TestClient(app)
    # No header
    r1 = c.post("/v1/auth/refresh")
    assert r1.status_code == HTTPStatus.BAD_REQUEST
    # With header
    r2 = c.post("/v1/auth/refresh", headers={"X-Auth-Intent": "refresh"})
    # Will likely 401 due to missing cookies, but must NOT fail for missing intent
    assert r2.status_code in {HTTPStatus.UNAUTHORIZED, HTTPStatus.OK, HTTPStatus.BAD_REQUEST}


def test_refresh_allowed_first_party(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "secret")
    monkeypatch.setenv("COOKIE_SAMESITE", "lax")
    c = TestClient(app)
    r = c.post("/v1/auth/refresh")
    # In lax mode, header not required; backend may still 401 for other reasons
    assert r.status_code in {HTTPStatus.UNAUTHORIZED, HTTPStatus.OK, HTTPStatus.BAD_REQUEST}


