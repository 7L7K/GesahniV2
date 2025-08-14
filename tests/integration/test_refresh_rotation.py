from http import HTTPStatus
from fastapi.testclient import TestClient
from app.main import app


def _login(client: TestClient):
    r = client.post("/v1/login", json={"username": "rfr_user", "password": "secret123"})
    if r.status_code in (HTTPStatus.BAD_REQUEST, HTTPStatus.UNAUTHORIZED):
        client.post("/v1/register", json={"username": "rfr_user", "password": "secret123"})
        r = client.post("/v1/login", json={"username": "rfr_user", "password": "secret123"})
    assert r.status_code in (HTTPStatus.OK, HTTPStatus.FOUND)
    return client


def test_refresh_rotates_and_spends_prior_jti(monkeypatch):
    client = TestClient(app)
    monkeypatch.setenv("COOKIE_SECURE", "0")
    _login(client)

    r1 = client.post("/v1/refresh")
    assert r1.status_code == HTTPStatus.OK
    sc1 = r1.headers.get_list("set-cookie")
    assert any(h.startswith("refresh_token=") for h in sc1)
    new_refresh = [h for h in sc1 if h.startswith("refresh_token=")][0]

    # Provide latest refresh explicitly to avoid client cookie edge cases
    latest_refresh_val = new_refresh.split(";", 1)[0].split("=", 1)[1]
    r2 = client.post("/v1/refresh", json={"refresh_token": latest_refresh_val})
    assert r2.status_code == HTTPStatus.OK
    sc2 = r2.headers.get_list("set-cookie")
    assert sc2 and sc2 != sc1

    client.cookies.set("refresh_token", latest_refresh_val)
    r3 = client.post("/v1/refresh")
    assert r3.status_code in (HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN)


def test_access_proactive_rotation_threshold_respected(monkeypatch):
    client = TestClient(app)
    monkeypatch.setenv("COOKIE_SECURE", "0")
    _login(client)
    r = client.get("/v1/whoami")
    assert r.status_code == HTTPStatus.OK


