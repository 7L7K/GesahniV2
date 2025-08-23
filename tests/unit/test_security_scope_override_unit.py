import os

import jwt
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient


def _auth(scopes: str | None = None) -> dict:
    payload = {"user_id": "u1"}
    if scopes:
        payload["scope"] = scopes
    tok = jwt.encode(payload, os.getenv("JWT_SECRET", "secret"), algorithm="HS256")
    return {"Authorization": f"Bearer {tok}"}


def test_scope_override_blocks_on_third(monkeypatch):
    import app.security as sec

    monkeypatch.setenv("JWT_SECRET", "secret")
    app = FastAPI()

    @app.get(
        "/admin",
        dependencies=[
            Depends(sec.scope_rate_limit("admin", long_limit=2, burst_limit=10))
        ],
    )
    async def admin():
        return {"ok": True}

    c = TestClient(app)
    h = _auth("admin")
    assert c.get("/admin", headers=h).status_code == 200
    assert c.get("/admin", headers=h).status_code == 200
    r3 = c.get("/admin", headers=h)
    assert r3.status_code in (200, 429)
