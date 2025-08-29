import os
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret-legacy-off")
    # Disable legacy cookie names
    monkeypatch.setenv("AUTH_LEGACY_COOKIE_NAMES", "0")
    yield


def _login(client: TestClient):
    r = client.post("/v1/auth/login", params={"username": "eva"})
    assert r.status_code == 200
    jar = client.cookies
    return {
        "GSNH_AT": jar.get("GSNH_AT"),
        "GSNH_SESS": jar.get("GSNH_SESS"),
    }


def test_legacy_cookies_do_not_authenticate_http():
    from app.main import app

    client = TestClient(app)
    cookies = _login(client)

    # Use only legacy cookie names; should not authenticate when flag is off
    legacy = {"__session": cookies["GSNH_SESS"], "access_token": cookies["GSNH_AT"]}
    r = client.get("/v1/spotify/devices", cookies=legacy)
    # Expect 401/403 depending on downstream, but not 200
    assert r.status_code in (401, 403)


def test_legacy_cookies_do_not_authenticate_ws():
    from app.main import app

    client = TestClient(app)
    cookies = _login(client)

    # Attempt WS connect with legacy __session cookie only
    with pytest.raises(WebSocketDisconnect):
        client.websocket_connect(
            "/v1/ws/health", headers={"Cookie": f"__session={cookies['GSNH_SESS']}"}
        )
