import os
import json
import contextlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    # Ensure predictable test env
    os.environ.setdefault("JWT_SECRET", "test-secret-phase1")
    os.environ.setdefault("AUTH_IDENTITY_BACKFILL", "1")
    os.environ.setdefault("AUTH_LEGACY_COOKIE_NAMES", "1")
    from app.main import app

    return TestClient(app)


def _login_and_get_cookies(client: TestClient, username: str = "alice"):
    r = client.post(f"/v1/auth/login", params={"username": username})
    assert r.status_code == 200
    # Collect cookies
    jar = client.cookies
    # Ensure expected cookies exist
    assert jar.get("GSNH_AT") is not None
    assert jar.get("GSNH_SESS") is not None
    return {
        "GSNH_AT": jar.get("GSNH_AT"),
        "GSNH_RT": jar.get("GSNH_RT"),
        "GSNH_SESS": jar.get("GSNH_SESS"),
    }


def test_session_only_http_auth_via_store_identity(client: TestClient):
    cookies = _login_and_get_cookies(client)

    # Drop access token cookie, keep only session id
    session_only = {"GSNH_SESS": cookies["GSNH_SESS"]}

    # whoami should authenticate via store identity (session_ready True)
    r = client.get("/v1/whoami", cookies=session_only)
    assert r.status_code == 200
    body = r.json()
    assert body.get("is_authenticated") is True
    assert body.get("session_ready") is True
    assert body.get("user_id") in {"alice", "dev", body.get("user", {}).get("id")}


def test_options_never_401_with_require_user(client: TestClient):
    # Endpoint guarded by require_user
    r = client.options("/v1/auth/clerk/protected")
    # Should not be 401
    assert r.status_code != 401


def test_ws_auth_with_canonical_session_cookie(client: TestClient):
    cookies = _login_and_get_cookies(client)

    with client.websocket_connect(
        "/v1/ws/health", headers={"Cookie": f"GSNH_SESS={cookies['GSNH_SESS']}"}
    ) as ws:
        msg = ws.receive_text()
        assert msg == "healthy"


def test_ws_auth_with_legacy_session_cookie(client: TestClient):
    cookies = _login_and_get_cookies(client)

    with client.websocket_connect(
        "/v1/ws/health", headers={"Cookie": f"__session={cookies['GSNH_SESS']}"}
    ) as ws:
        msg = ws.receive_text()
        assert msg == "healthy"


def test_store_outage_session_only_503_but_header_passes(
    client: TestClient, monkeypatch
):
    cookies = _login_and_get_cookies(client, username="bob")

    # Monkeypatch Redis client to simulate outage for session identity reads
    from app import session_store as ss

    store = ss.get_session_store()

    class FailingRedis:
        def get(self, key):
            raise RuntimeError("simulated outage")

    # Force a redis client presence and failure
    monkeypatch.setattr(store, "_redis_client", FailingRedis())

    # Session-only request should yield 503 on a protected route (verify_token)
    session_only = {"GSNH_SESS": cookies["GSNH_SESS"]}
    # Choose a protected route that depends on verify_token but is lightweight
    # We'll use Spotify status endpoint which is guarded by verify_token.
    r = client.get("/v1/spotify/devices", cookies=session_only)
    assert r.status_code == 503

    # With valid Authorization header, request should pass auth layer (even if upstream may fail for other reasons)
    at = cookies["GSNH_AT"]
    r2 = client.get("/v1/spotify/devices", headers={"Authorization": f"Bearer {at}"})
    # Auth passes; endpoint may still return 502/401 due to provider, accept non-401/503 here
    assert r2.status_code not in (401, 503)


def test_lazy_refresh_sets_new_access_token_cookie(client: TestClient):
    cookies = _login_and_get_cookies(client, username="carol")
    # Construct jar with only refresh + session
    jar = {"GSNH_RT": cookies.get("GSNH_RT"), "GSNH_SESS": cookies.get("GSNH_SESS")}
    # Call endpoint that depends on get_current_user_id (injects Response)
    r = client.get("/v1/me", cookies=jar)
    assert r.status_code == 200
    # Verify Set-Cookie includes a fresh GSNH_AT
    set_cookie_headers = (
        r.headers.get_all("set-cookie")
        if hasattr(r.headers, "get_all")
        else r.headers.get("set-cookie", "")
    )
    if isinstance(set_cookie_headers, list):
        hdrs = set_cookie_headers
    else:
        hdrs = [set_cookie_headers] if set_cookie_headers else []
    assert any(
        "GSNH_AT=" in h and "Max-Age" in h for h in hdrs
    ), f"Set-Cookie did not include GSNH_AT: {hdrs}"
