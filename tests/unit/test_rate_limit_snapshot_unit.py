from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient


def test_rate_limit_snapshot_headers_present():
    from app.security import rate_limit
    from app.main import app

    c = TestClient(app)
    r = c.get("/v1/healthz")
    assert r.status_code == 200
    assert r.headers.get("X-RateLimit-Limit") is not None
    assert r.headers.get("X-RateLimit-Remaining") is not None
    # Ensure request id and basic headers are present
    assert r.headers.get("X-Request-ID")


