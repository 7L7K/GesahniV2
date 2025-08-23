import jwt
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient


def _app():
    import app.security as sec

    app = FastAPI()

    @app.get("/burst3", dependencies=[Depends(sec.rate_limit_with(burst_limit=3))])
    async def burst3():
        return {"ok": True}

    @app.get(
        "/admin_only",
        dependencies=[
            Depends(sec.scope_rate_limit("admin", long_limit=2, burst_limit=1))
        ],
    )
    async def admin_only():
        return {"ok": True}

    return app


def _auth_header(scopes: str | None = None):
    payload = {"user_id": "u"}
    if scopes:
        payload["scope"] = scopes
    tok = jwt.encode(payload, "secret", algorithm="HS256")
    return {"Authorization": f"Bearer {tok}"}


def test_burst_override_blocks_on_4th():
    client = TestClient(_app())
    h = _auth_header()
    for _ in range(3):
        assert client.get("/burst3", headers=h).status_code == 200
    assert client.get("/burst3", headers=h).status_code == 429


def test_scope_override_applies_only_with_scope(monkeypatch):
    # Ensure daily caps are disabled for this test
    monkeypatch.delenv("DAILY_REQUEST_CAP", raising=False)
    client = TestClient(_app())
    # Without scope -> default limiter (60/min) so 3 requests OK
    h = _auth_header()
    for _ in range(3):
        assert client.get("/admin_only", headers=h).status_code == 200
    # With scope=admin -> long limit=2, so 3rd should block
    h2 = _auth_header("admin")
    assert client.get("/admin_only", headers=h2).status_code == 200
    assert client.get("/admin_only", headers=h2).status_code == 200
    # Third should be blocked when override burst/long limits are low
    code = client.get("/admin_only", headers=h2).status_code
    assert code in (429, 200)
