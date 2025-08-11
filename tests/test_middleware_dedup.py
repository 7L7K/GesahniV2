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


