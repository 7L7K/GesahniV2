from http import HTTPStatus
import time
import jwt

from fastapi.testclient import TestClient

from app.main import app


def _mint(secret: str, sub: str, ttl_s: int = 300) -> str:
    now = int(time.time())
    payload = {"user_id": sub, "sub": sub, "iat": now, "exp": now + ttl_s}
    return jwt.encode(payload, secret, algorithm="HS256")


def test_cookie_only_session_ready(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret-key-for-testing-only-not-for-production")
    c = TestClient(app)
    tok = _mint("test-secret-key-for-testing-only-not-for-production", "alice")
    c.cookies.set("access_token", tok)
    r = c.get("/v1/whoami")
    assert r.status_code == HTTPStatus.OK
    body = r.json()
    assert body["is_authenticated"] is True
    assert body["session_ready"] is True
    assert body["source"] == "cookie"
    assert body["user"]["id"] == "alice"


def test_header_only_session_ready(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret-key-for-testing-only-not-for-production")
    c = TestClient(app)
    tok = _mint("test-secret-key-for-testing-only-not-for-production", "bob")
    r = c.get("/v1/whoami", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == HTTPStatus.OK
    body = r.json()
    assert body["is_authenticated"] is True
    assert body["session_ready"] is True
    assert body["source"] == "header"
    assert body["user"]["id"] == "bob"


def test_neither_token(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret-key-for-testing-only-not-for-production")
    c = TestClient(app)
    r = c.get("/v1/whoami")
    # We tolerate 200 with session_ready=false to ease UX
    assert r.status_code == HTTPStatus.OK
    body = r.json()
    assert body["is_authenticated"] is False
    assert body["session_ready"] is False
    assert body["user"]["id"] is None


def test_expired_access_token(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret-key-for-testing-only-not-for-production")
    c = TestClient(app)
    # ttl -1 to force expiry
    tok = _mint("test-secret-key-for-testing-only-not-for-production", "expired", ttl_s=-1)
    c.cookies.set("access_token", tok)
    r = c.get("/v1/whoami")
    assert r.status_code == HTTPStatus.OK
    body = r.json()
    assert body["is_authenticated"] is False
    assert body["session_ready"] is False
    assert body["user"]["id"] is None


