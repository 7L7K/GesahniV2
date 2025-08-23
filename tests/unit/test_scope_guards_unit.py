from __future__ import annotations

import os

import jwt
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.deps.scopes import require_scope
from app.security import verify_token


def _app():
    os.environ.setdefault("JWT_SECRET", "secret")
    app = FastAPI()

    @app.get(
        "/admin",
        dependencies=[Depends(verify_token), Depends(require_scope("admin:write"))],
    )
    async def admin():
        return {"ok": True}

    return app


def test_scope_guard_denies_without_scope():
    c = TestClient(_app())
    token = jwt.encode(
        {"user_id": "u", "scope": "music:control"},
        os.getenv("JWT_SECRET", "secret"),
        algorithm="HS256",
    )
    r = c.get("/admin", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403

    token2 = jwt.encode(
        {"user_id": "u", "scope": "music:control admin:write"},
        os.getenv("JWT_SECRET", "secret"),
        algorithm="HS256",
    )
    r2 = c.get("/admin", headers={"Authorization": f"Bearer {token2}"})
    assert r2.status_code == 200
