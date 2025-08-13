from __future__ import annotations

import os
from fastapi.testclient import TestClient
from fastapi import FastAPI

from app.csrf import CSRFMiddleware


def _app():
    os.environ.setdefault("CSRF_ENABLED", "1")
    a = FastAPI()
    a.add_middleware(CSRFMiddleware)

    @a.get("/ping")
    async def ping():
        return {"ok": True}

    @a.post("/post")
    async def post():
        return {"ok": True}

    return a


def test_csrf_allows_get_blocks_post_without_token():
    c = TestClient(_app())
    assert c.get("/ping").status_code == 200
    r = c.post("/post")
    assert r.status_code == 403


def test_csrf_allows_post_with_matching_token():
    c = TestClient(_app())
    # Set cookie and header to same token
    t = "abc123"
    c.cookies.set("csrf_token", t)
    r = c.post("/post", headers={"X-CSRF-Token": t})
    assert r.status_code == 200


