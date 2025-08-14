from http import HTTPStatus
from fastapi.testclient import TestClient

from app.main import app


def test_cookie_priority_fallback(monkeypatch):
    # Force helper to throw to trigger fallback
    import app.api.auth as auth_api
    monkeypatch.setattr(auth_api, "_append_cookie_with_priority", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setenv("COOKIE_SECURE", "0")
    c = TestClient(app)
    c.post("/v1/register", json={"username": "carol", "password": "secret123"})
    r = c.post("/v1/login", json={"username": "carol", "password": "secret123"})
    assert r.status_code in (HTTPStatus.OK, HTTPStatus.FOUND)
    set_cookies = r.headers.get_list("set-cookie")
    # Fallback must still set HttpOnly and SameSite attributes
    assert any("HttpOnly" in h for h in set_cookies)
    assert any("SameSite=" in h for h in set_cookies)


