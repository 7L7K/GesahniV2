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


def test_bypass_scope_global_env(monkeypatch):
    import app.security as sec

    monkeypatch.setenv("JWT_SECRET", "secret")
    monkeypatch.setenv("RATE_LIMIT_BYPASS_SCOPES", "admin")
    app = FastAPI()

    @app.get("/ping", dependencies=[Depends(sec.rate_limit)])
    async def ping():
        return {"ok": True}

    c = TestClient(app)
    r = c.get("/ping", headers=_auth("admin"))
    assert r.status_code == 200


def test_daily_cap_blocks(monkeypatch):
    import app.security as sec

    monkeypatch.setenv("JWT_SECRET", "secret")
    monkeypatch.setenv("DAILY_REQUEST_CAP", "2")
    monkeypatch.setenv("RATE_LIMIT_PER_MIN", "1000")
    app = FastAPI()

    @app.get("/ping", dependencies=[Depends(sec.rate_limit)])
    async def ping():
        return {"ok": True}

    c = TestClient(app)
    h = _auth()
    assert c.get("/ping", headers=h).status_code == 200
    assert c.get("/ping", headers=h).status_code == 200
    r3 = c.get("/ping", headers=h)
    assert r3.status_code == 429
