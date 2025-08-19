from __future__ import annotations

import os
from fastapi.testclient import TestClient
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from app.csrf import CSRFMiddleware


def _app():
    # Explicitly set CSRF_ENABLED to ensure it's enabled
    os.environ["CSRF_ENABLED"] = "1"
    a = FastAPI()
    
    # Add CORS middleware first (handles preflights)
    a.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )
    
    # Add CSRF middleware after CORS (handles non-OPTIONS requests)
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


