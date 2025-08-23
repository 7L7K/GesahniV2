from fastapi import FastAPI, Request
from fastapi.testclient import TestClient


def test_rate_limit_problem_returns_problem_json(monkeypatch):
    import app.security as sec

    monkeypatch.setenv("RATE_LIMIT_BACKEND", "memory")
    app = FastAPI()

    @app.get("/limited")
    async def limited(request: Request):
        await sec.rate_limit_problem(
            request, long_limit=1, burst_limit=1, window_s=30.0
        )
        return {"ok": True}

    c = TestClient(app)
    assert c.get("/limited").status_code == 200
    r2 = c.get("/limited")
    assert r2.status_code == 429
    assert r2.headers.get("Content-Type", "").startswith("application/problem+json")
    assert r2.headers.get("X-RateLimit-Remaining") is not None
    body = r2.json()
    assert body.get("status") == 429 and body.get("title") == "Too Many Requests"
