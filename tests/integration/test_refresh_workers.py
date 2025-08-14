from http import HTTPStatus
from fastapi.testclient import TestClient
from app.main import app
import time


def _setup(monkeypatch):
    monkeypatch.setenv("COOKIE_SECURE", "0")
    c = TestClient(app)
    c.post("/v1/register", json={"username": "wrk_user", "password": "secret123"})
    r = c.post("/v1/login", json={"username": "wrk_user", "password": "secret123"})
    assert r.status_code in (HTTPStatus.OK, HTTPStatus.FOUND)
    return c


def test_concurrent_refresh_simulated_workers(monkeypatch):
    c = _setup(monkeypatch)
    # Simulate 5 parallel workers with tiny stagger
    from concurrent.futures import ThreadPoolExecutor

    def _call(delay_ms: int):
        time.sleep(delay_ms / 1000.0)
        return c.post("/v1/auth/refresh", headers={"X-Auth-Intent": "refresh"}).status_code

    with ThreadPoolExecutor(max_workers=5) as ex:
        futures = [ex.submit(_call, i * 5) for i in range(5)]
        codes = sorted([f.result() for f in futures])
    # Expect one success and the rest 401
    assert codes.count(HTTPStatus.OK) == 1
    assert codes.count(HTTPStatus.UNAUTHORIZED) == 4


def test_csrf_intent_required_in_none(monkeypatch):
    c = _setup(monkeypatch)
    monkeypatch.setenv("COOKIE_SAMESITE", "none")
    # Missing header
    r1 = c.post("/v1/auth/refresh")
    assert r1.status_code in (HTTPStatus.BAD_REQUEST, HTTPStatus.UNAUTHORIZED)
    # With header
    r2 = c.post("/v1/auth/refresh", headers={"X-Auth-Intent": "refresh"})
    assert r2.status_code == HTTPStatus.OK


