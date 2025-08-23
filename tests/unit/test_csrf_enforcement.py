import os

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.csrf import CSRFMiddleware


def _app():
    os.environ["CSRF_ENABLED"] = "1"
    a = FastAPI()
    a.add_middleware(CSRFMiddleware)

    @a.post("/change")
    async def change():
        return {"ok": True}

    return a


def test_post_without_cookie_or_header_returns_403():
    c = TestClient(_app())
    r = c.post("/change")
    assert r.status_code == 403


def test_post_with_cookie_but_missing_header_returns_403():
    c = TestClient(_app())
    c.cookies.set("csrf_token", "tok")
    r = c.post("/change")
    assert r.status_code == 403


def test_post_with_matching_cookie_and_header_passes():
    c = TestClient(_app())
    c.cookies.set("csrf_token", "tok")
    r = c.post("/change", headers={"X-CSRF-Token": "tok"})
    assert r.status_code == 200
