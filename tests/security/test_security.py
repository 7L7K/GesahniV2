from __future__ import annotations

import os

import jwt
from fastapi import Depends, FastAPI, Request
from fastapi.testclient import TestClient

from app.main import app


def _make_jwt(payload: dict) -> str:
    secret = os.getenv("JWT_SECRET", "test-secret")
    return jwt.encode(payload, secret, algorithm="HS256")


def test_preflight_endpoint_available():
    client = TestClient(app)
    r = client.get("/v1/status/preflight")
    assert r.status_code == 200
    data = r.json()
    assert "ok" in data and "checks" in data


def test_rate_limit_key_scope_route_isolates(monkeypatch):
    os.environ["RATE_LIMIT_KEY_SCOPE"] = "route"
    os.environ["RATE_LIMIT_PER_MIN"] = "2"
    from importlib import reload

    import app.security as sec

    reload(sec)
    client = TestClient(app)
    # Hit two different routes within window – both should pass since keys differ
    r1 = client.get("/healthz")
    r2 = client.get("/v1/status/features")
    assert r1.status_code == 200
    assert r2.status_code in {200, 401, 403}  # may require auth; only ensure not 429


def test_verify_token_cookie_and_header_paths(monkeypatch):
    os.environ["JWT_SECRET"] = "test-secret"
    client = TestClient(app)
    tok = _make_jwt({"user_id": "u1"})
    # Header path
    r1 = client.get("/healthz", headers={"Authorization": f"Bearer {tok}"})
    assert r1.status_code == 200
    # Cookie path
    client.cookies.set("GSNH_AT", tok)
    r2 = client.get("/healthz")
    assert r2.status_code == 200


def test_rate_limit_blocks_and_retry_after(monkeypatch):
    import app.security as sec

    api = FastAPI()

    async def custom_limits(request: Request):
        request.state.rate_limit_long_limit = 1
        request.state.rate_limit_burst_limit = 1
        return None

    @api.get("/ping", dependencies=[Depends(custom_limits), Depends(sec.rate_limit)])
    async def ping():
        return {"ok": True}

    c = TestClient(api)
    assert c.get("/ping").status_code == 200
    r2 = c.get("/ping")
    assert r2.status_code == 429
    assert "Retry-After" in r2.headers


import asyncio


def test_webhook_sign_verify_roundtrip(tmp_path, monkeypatch):
    # Configure file-based secret
    path = tmp_path / "ha.txt"
    path.write_text("abc123\n")
    monkeypatch.setenv("HA_WEBHOOK_SECRET_FILE", str(path))
    TestClient(app)

    # Minimal endpoint to exercise verify_webhook through the router
    body = b"hello"
    from app.security.webhooks import sign_webhook

    sig = sign_webhook(body, "abc123")
    # Call underlying function via FastAPI dependency path is complex; directly exercise
    from starlette.requests import Request

    from app.security.webhooks import verify_webhook

    async def _run():
        scope = {
            "type": "http",
            "method": "POST",
            "path": "/",
            "headers": [(b"x-signature", sig.encode())],
        }
        req = Request(scope)
        req._body = body  # type: ignore[attr-defined]
        out = await verify_webhook(req, x_signature=sig)
        assert out == body

    asyncio.run(_run())
