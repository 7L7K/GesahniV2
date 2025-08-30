from http import HTTPStatus

from fastapi.testclient import TestClient

from app.main import app


def test_profile_mutation_requires_csrf(monkeypatch):
    client = TestClient(app)
    # Ensure dev cookie semantics for TestClient over http
    monkeypatch.setenv("COOKIE_SECURE", "0")
    monkeypatch.setenv("CSRF_ENABLED", "1")

    # First get a CSRF token (should work without auth)
    cr = client.get("/v1/csrf")
    assert cr.status_code == HTTPStatus.OK
    token = cr.json()["csrf_token"]

    # Now login with CSRF token
    lr = client.post(
        "/v1/login",
        json={"username": "king", "password": "secret123"},
        headers={"X-CSRF-Token": token}
    )
    if lr.status_code in (HTTPStatus.BAD_REQUEST, HTTPStatus.UNAUTHORIZED):
        # Try registering with CSRF token
        client.post(
            "/v1/register",
            json={"username": "king", "password": "secret123"},
            headers={"X-CSRF-Token": token}
        )
        lr = client.post(
            "/v1/login",
            json={"username": "king", "password": "secret123"},
            headers={"X-CSRF-Token": token}
        )
    assert lr.status_code in (HTTPStatus.OK, HTTPStatus.FOUND)

    r1 = client.post("/v1/profile", json={"display_name": "King"})
    assert r1.status_code in (HTTPStatus.BAD_REQUEST, HTTPStatus.FORBIDDEN)

    cr = client.get("/v1/csrf")
    assert cr.status_code == HTTPStatus.OK
    token = cr.json()["csrf_token"]

    r2 = client.post(
        "/v1/profile", headers={"X-CSRF-Token": token}, json={"display_name": "King"}
    )
    assert r2.status_code == HTTPStatus.OK
