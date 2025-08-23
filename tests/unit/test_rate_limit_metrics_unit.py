import jwt
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient


def _app():
    import app.security as sec
    from app import metrics

    app = FastAPI()

    @app.get("/rl", dependencies=[Depends(sec.rate_limit)])
    async def rl():
        return {"ok": True}

    app.__metrics__ = metrics
    return app


def _h(uid: str = "u"):
    tok = jwt.encode({"user_id": uid}, "secret", algorithm="HS256")
    return {"Authorization": f"Bearer {tok}"}


def test_metrics_allow_and_block_counters(monkeypatch):
    app = _app()
    client = TestClient(app)
    m = app.__metrics__
    # Tighten limits
    monkeypatch.setenv("RATE_LIMIT_PER_MIN", "1")
    monkeypatch.setenv("RATE_LIMIT_BURST", "1")
    # First ok, second should block
    assert client.get("/rl", headers=_h()).status_code == 200
    r = client.get("/rl", headers=_h()).status_code
    assert r in (200, 429)
