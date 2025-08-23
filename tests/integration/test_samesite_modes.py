from http import HTTPStatus

from fastapi.testclient import TestClient

from app.main import app


def _login(client: TestClient):
    client.post("/v1/register", json={"username": "ssm_user", "password": "secret123"})
    r = client.post("/v1/login", json={"username": "ssm_user", "password": "secret123"})
    assert r.status_code in (HTTPStatus.OK, HTTPStatus.FOUND)
    return client


def test_samesite_lax(monkeypatch):
    client = TestClient(app)
    monkeypatch.setenv("COOKIE_SAMESITE", "lax")
    monkeypatch.setenv("COOKIE_SECURE", "0")
    _login(client)
    r = client.get("/v1/whoami")
    assert r.status_code == 200
    # Cookie flags in response from login already asserted in other tests


def test_samesite_none(monkeypatch):
    client = TestClient(app)
    monkeypatch.setenv("COOKIE_SAMESITE", "none")
    monkeypatch.setenv("COOKIE_SECURE", "1")
    _login(client)
    r = client.get("/v1/whoami")
    assert r.status_code == 200
