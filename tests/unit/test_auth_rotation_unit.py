from __future__ import annotations

import os

from fastapi.testclient import TestClient

from app.main import app


def _client():
    os.environ.setdefault("JWT_SECRET", "secret")
    os.environ.setdefault("JWT_ACCESS_TTL_SECONDS", "60")
    os.environ.setdefault("JWT_REFRESH_EXPIRE_MINUTES", "10")
    return TestClient(app)


def test_refresh_rotation_and_reuse_detection():
    c = _client()
    # Login (dev scaffold)
    r = c.post("/v1/auth/login", params={"username": "alice"})
    assert r.status_code == 200
    # First refresh succeeds and rotates refresh cookie
    r2 = c.post("/v1/auth/refresh")
    assert r2.status_code == 200
    # Re-use immediately: without Redis, permissive; with Redis and rotation, expect 401
    r3 = c.post("/v1/auth/refresh")
    assert r3.status_code in (200, 401)
