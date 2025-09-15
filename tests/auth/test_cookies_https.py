from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_auth_cookies_secure_in_https_context(monkeypatch):
    c = TestClient(app, base_url="https://testserver")
    # Force secure cookie mode
    monkeypatch.setenv("COOKIE_SECURE", "1")
    # router mounted under /v1
    r = c.post("/v1/auth/login", params={"username": "alice"})
    assert r.status_code == 200
    # Both access_token cookies should be present and Secure
    cookies = r.headers.get("set-cookie", "")
    assert "access_token=" in cookies
    assert "Secure" in cookies or "secure" in cookies
