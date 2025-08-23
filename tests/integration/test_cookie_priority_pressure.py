from http import HTTPStatus

from fastapi.testclient import TestClient

from app.main import app


def test_cookie_pressure_priority(monkeypatch):
    monkeypatch.setenv("COOKIE_SECURE", "0")
    c = TestClient(app)
    c.post("/v1/register", json={"username": "cp_user", "password": "secret123"})
    r = c.post("/v1/login", json={"username": "cp_user", "password": "secret123"})
    assert r.status_code in (HTTPStatus.OK, HTTPStatus.FOUND)

    # Blast 50 low-priority cookies from server side (simulate set)
    for i in range(50):
        # Use helper endpoint behavior: set cookie name 'junk<i>'
        # In absence of a dedicated endpoint, add them to the client directly
        c.cookies.set(f"junk{i}", "1")

    # Whoami should still see auth session
    who = c.get("/v1/whoami")
    assert who.status_code == 200
    body = who.json()
    assert body.get("is_authenticated") is True
