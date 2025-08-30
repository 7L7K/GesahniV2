from http import HTTPStatus

from fastapi.testclient import TestClient

from app.main import app


def test_cookie_priority_flags_after_login(monkeypatch):
    monkeypatch.setenv("COOKIE_SECURE", "0")
    c = TestClient(app)
    # Ensure user exists
    c.post("/v1/register", json={"username": "alice", "password": "secret123"})
    r = c.post("/v1/login", json={"username": "alice", "password": "secret123"})
    assert r.status_code in (HTTPStatus.OK, HTTPStatus.FOUND)
    set_cookies = r.headers.get_list("set-cookie")
    # Check for canonical cookie names with priority
    assert any("GSNH_AT=" in h for h in set_cookies)
    assert any("GSNH_RT=" in h for h in set_cookies)
    assert any("GSNH_SESS=" in h for h in set_cookies)
    # Ensure all auth cookies have Priority=High
    priority_count = sum(1 for h in set_cookies if "Priority=High" in h)
    assert priority_count >= 3  # At least 3 auth cookies should have high priority
