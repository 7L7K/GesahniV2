from http import HTTPStatus

from fastapi.testclient import TestClient

from app.main import app


def test_profile_mutation_requires_csrf(monkeypatch):
    client = TestClient(app)
    # Ensure dev cookie semantics for TestClient over http
    monkeypatch.setenv("COOKIE_SECURE", "0")
    # Login (register if needed)
    lr = client.post("/v1/login", json={"username": "king", "password": "secret123"})
    if lr.status_code in (HTTPStatus.BAD_REQUEST, HTTPStatus.UNAUTHORIZED):
        client.post("/v1/register", json={"username": "king", "password": "secret123"})
        lr = client.post("/v1/login", json={"username": "king", "password": "secret123"})
    assert lr.status_code in (HTTPStatus.OK, HTTPStatus.FOUND)

    r1 = client.post("/v1/profile", json={"display_name": "King"})
    assert r1.status_code in (HTTPStatus.BAD_REQUEST, HTTPStatus.FORBIDDEN)

    cr = client.get("/v1/csrf")
    assert cr.status_code == HTTPStatus.OK
    token = cr.json()["csrf_token"]

    r2 = client.post("/v1/profile", headers={"X-CSRF-Token": token}, json={"display_name": "King"})
    assert r2.status_code == HTTPStatus.OK


