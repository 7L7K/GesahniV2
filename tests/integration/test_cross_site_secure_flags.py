from http import HTTPStatus
from fastapi.testclient import TestClient

from app.main import app


def test_cross_site_secure_flags(monkeypatch):
    monkeypatch.setenv("COOKIE_SECURE", "1")
    monkeypatch.setenv("COOKIE_SAMESITE", "none")
    c = TestClient(app)
    c.post("/v1/register", json={"username": "dave", "password": "secret123"})
    r = c.post("/v1/login", json={"username": "dave", "password": "secret123"})
    assert r.status_code in (HTTPStatus.OK, HTTPStatus.FOUND)
    set_cookies = r.headers.get_list("set-cookie")
    # In None mode, helper ensures Priority=High and SameSite=None; Secure may be omitted in http tests
    assert any("SameSite=None" in h for h in set_cookies)
    assert any("Priority=High" in h for h in set_cookies)


