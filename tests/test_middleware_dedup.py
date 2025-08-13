import os
from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_dedup_middleware_basic(monkeypatch):
    # Build a tiny app with the middleware and a trivial handler
    from app.middleware import DedupMiddleware

    app = FastAPI()
    app.add_middleware(DedupMiddleware)

    @app.get("/ping")
    async def ping():
        return {"pong": True}

    client = TestClient(app)
    headers = {"X-Request-ID": "same-id"}
    # First request accepted
    r1 = client.get("/ping", headers=headers)
    assert r1.status_code == 200
    # Immediate duplicate rejected with 409
    r2 = client.get("/ping", headers=headers)
    assert r2.status_code == 409
    # Include Retry-After hint
    assert r2.headers.get("Retry-After") is not None


def test_dedup_ttl_expiry(monkeypatch):
    from app.middleware import DedupMiddleware

    monkeypatch.setenv("DEDUP_TTL_SECONDS", "1")
    app = FastAPI()
    app.add_middleware(DedupMiddleware)

    @app.get("/ping")
    async def ping():
        return {"pong": True}

    client = TestClient(app)
    h = {"X-Request-ID": "rid-ttl"}
    assert client.get("/ping", headers=h).status_code == 200
    assert client.get("/ping", headers=h).status_code == 409
    import time as _t
    _t.sleep(1.1)
    # After TTL, request should be accepted again
    assert client.get("/ping", headers=h).status_code == 200


