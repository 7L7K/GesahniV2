import os
from pathlib import Path

import jwt
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient


def _app_with_security(monkeypatch, extra_env: dict | None = None):
    monkeypatch.setenv("JWT_SECRET", "secret")
    if extra_env:
        for k, v in extra_env.items():
            monkeypatch.setenv(k, str(v))

    import app.security as sec
    # clear buckets to avoid bleed between tests
    sec._http_requests.clear()
    sec.http_burst.clear()

    app = FastAPI()

    @app.get("/protected")
    async def protected(dep1: None = Depends(sec.verify_token), dep2: None = Depends(sec.rate_limit)):
        return {"ok": True}

    @app.post("/state")
    async def state(dep: None = Depends(sec.require_nonce)):
        return {"ok": True}

    @app.post("/ha/webhook")
    async def webhook(body: bytes = Depends(sec.verify_webhook)):
        return {"len": len(body)}

    client = TestClient(app)
    return client, sec.rotate_webhook_secret


def _auth_header(uid: str = "u") -> dict:
    token = jwt.encode({"user_id": uid}, "secret", algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


def test_rate_limit_long_and_burst(monkeypatch):
    client, _ = _app_with_security(monkeypatch)
    h = _auth_header()
    # default burst window allows 10 rapid requests, the 11th should 429
    for _ in range(10):
        assert client.get("/protected", headers=h).status_code == 200
    r = client.get("/protected", headers=h)
    assert r.status_code == 429
    assert r.headers.get("Retry-After") is not None


def test_response_has_security_headers(monkeypatch):
    # Build a minimal app that includes the tracing middleware which sets headers
    from fastapi import FastAPI
    from app.middleware import trace_request

    app = FastAPI()

    @app.get("/pong")
    async def pong():
        return {"ok": True}

    app.middleware("http")(trace_request)
    client = TestClient(app)
    r = client.get("/pong")
    assert r.status_code == 200
    # Basic hardening headers should be present
    assert "Content-Security-Policy" in r.headers
    assert r.headers.get("X-Content-Type-Options") == "nosniff"
    assert r.headers.get("Referrer-Policy") is not None
    assert r.headers.get("X-Frame-Options") == "DENY"


def test_nonce_required_and_reuse(monkeypatch):
    client, _ = _app_with_security(monkeypatch, {"REQUIRE_NONCE": "1", "NONCE_TTL_SECONDS": "5"})
    # missing header
    r = client.post("/state")
    assert r.status_code == 400
    # single use
    r = client.post("/state", headers={"X-Nonce": "abc"})
    assert r.status_code == 200
    # reuse rejected
    r = client.post("/state", headers={"X-Nonce": "abc"})
    assert r.status_code == 409


def test_webhook_signing_and_rotation(monkeypatch, tmp_path: Path):
    secret_file = tmp_path / "sec.txt"
    client, rotate = _app_with_security(
        monkeypatch,
        {"HA_WEBHOOK_SECRET_FILE": str(secret_file)},
    )

    # write an initial secret
    s1 = rotate()
    body = b"{}"
    import hmac, hashlib

    sig = hmac.new(s1.encode(), body, hashlib.sha256).hexdigest()
    r = client.post("/ha/webhook", data=body, headers={"X-Signature": sig})
    assert r.status_code == 200

    # rotate adds new secret at top; old still valid
    s2 = rotate()
    sig2 = hmac.new(s2.encode(), body, hashlib.sha256).hexdigest()
    assert client.post("/ha/webhook", data=body, headers={"X-Signature": sig2}).status_code == 200
    # old still accepted for a time
    assert client.post("/ha/webhook", data=body, headers={"X-Signature": sig}).status_code == 200


