from http import HTTPStatus

import pytest
from fastapi.testclient import TestClient

from app.main import app


def _setup(client: TestClient):
    # CSRF optional for this test path
    client.post("/v1/register", json={"username": "rre_user", "password": "secret123"})
    client.post("/v1/login", json={"username": "rre_user", "password": "secret123"})


@pytest.mark.contract
def test_refresh_replay_header_mode(monkeypatch):
    monkeypatch.setenv("CSRF_ENABLED", "0")
    client = TestClient(app)
    with client:
        _setup(client)
        # Capture current refresh cookie value
        ref = client.cookies.get("refresh_token")
        assert ref, "missing refresh_token cookie after login"
        # First use should succeed
        r1 = client.post("/v1/auth/refresh", json={"refresh_token": ref})
        assert r1.status_code in (HTTPStatus.OK, HTTPStatus.NO_CONTENT)
        # Second use must 401
        r2 = client.post("/v1/auth/refresh", json={"refresh_token": ref})
        assert r2.status_code == HTTPStatus.UNAUTHORIZED


from fastapi.testclient import TestClient


def _bootstrap(client: TestClient):
    # ensure user and cookies
    client.post("/v1/register", json={"username": "rr_user", "password": "secret123"})
    r = client.post("/v1/login", json={"username": "rr_user", "password": "secret123"})
    assert r.status_code in (HTTPStatus.OK, HTTPStatus.FOUND)
    return client


def test_refresh_replay_sequential(monkeypatch):
    client = TestClient(app)
    monkeypatch.setenv("COOKIE_SECURE", "0")
    _bootstrap(client)

    # capture original refresh before rotation
    orig_refresh = client.cookies.get("refresh_token")
    assert orig_refresh

    r1 = client.post("/v1/auth/refresh")
    assert r1.status_code == HTTPStatus.OK
    # Reuse the same refresh token that was just spent
    client.cookies.set("refresh_token", orig_refresh)
    r2 = client.post("/v1/auth/refresh")
    assert r2.status_code == HTTPStatus.UNAUTHORIZED


def test_refresh_race_two_inflight(monkeypatch):
    client = TestClient(app)
    monkeypatch.setenv("COOKIE_SECURE", "0")
    _bootstrap(client)

    # Fire two concurrent refresh calls
    from concurrent.futures import ThreadPoolExecutor

    def _call():
        return client.post("/v1/auth/refresh").status_code

    with ThreadPoolExecutor(max_workers=2) as ex:
        a = ex.submit(_call)
        b = ex.submit(_call)
        codes = sorted([a.result(), b.result()])
    assert codes == [HTTPStatus.OK, HTTPStatus.UNAUTHORIZED]
