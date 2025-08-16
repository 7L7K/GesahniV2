from http import HTTPStatus
from fastapi.testclient import TestClient
from app.main import app


def test_logout_clears_and_blocks_refresh(monkeypatch):
    client = TestClient(app)
    monkeypatch.setenv("COOKIE_SECURE", "0")
    client.post("/v1/register", json={"username": "lo_user", "password": "secret123"})
    r = client.post("/v1/login", json={"username": "lo_user", "password": "secret123"})
    assert r.status_code in (HTTPStatus.OK, HTTPStatus.FOUND)

    # logout
    r2 = client.post("/v1/auth/logout")
    assert r2.status_code == HTTPStatus.NO_CONTENT  # 204 is correct for logout

    # cookies should be gone (client-side helper can't read httponly, but server behavior next proves it)
    r3 = client.get("/v1/whoami")
    # whoami returns JSON but not authenticated; accept 200 with is_authenticated false
    assert r3.status_code in (HTTPStatus.OK, HTTPStatus.UNAUTHORIZED)

    # refresh now denied
    r4 = client.post("/v1/auth/refresh")
    assert r4.status_code == HTTPStatus.UNAUTHORIZED


