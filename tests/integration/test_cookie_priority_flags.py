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
    assert any("access_token=" in h for h in set_cookies)
    assert any("Priority=High" in h for h in set_cookies)


