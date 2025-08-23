import jwt
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient


def _app():
    import app.security as sec

    app = FastAPI()

    @app.get("/rl", dependencies=[Depends(sec.rate_limit)])
    async def rl():
        return {"ok": True}

    return app


def _header(scope: str | None = None, uid: str = "u"):
    payload = {"user_id": uid}
    if scope:
        payload["scope"] = scope
    token = jwt.encode(payload, "secret", algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


def test_bypass_scopes_allows(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_BYPASS_SCOPES", "admin support")
    monkeypatch.setenv("DAILY_REQUEST_CAP", "0")
    client = TestClient(_app())
    h = _header("admin")
    for _ in range(10):
        assert client.get("/rl", headers=h).status_code == 200


def test_daily_cap_blocks(monkeypatch):
    monkeypatch.setenv("DAILY_REQUEST_CAP", "2")
    client = TestClient(_app())
    h = _header(None, uid="daily_user")
    assert client.get("/rl", headers=h).status_code == 200
    assert client.get("/rl", headers=h).status_code == 200
    # 3rd should be blocked by daily cap
    r = client.get("/rl", headers=h)
    assert r.status_code == 429
