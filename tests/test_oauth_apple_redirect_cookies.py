import os
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _make_client(monkeypatch):
    # Configure minimal env so jwt.encode works and callback path is wired
    monkeypatch.setenv("JWT_SECRET", "testsecret")
    monkeypatch.setenv("APPLE_CLIENT_ID", "cid")
    monkeypatch.setenv("APPLE_TEAM_ID", "tid")
    monkeypatch.setenv("APPLE_KEY_ID", "kid")
    # Private key is not used when we stub the signer below
    monkeypatch.setenv("APPLE_PRIVATE_KEY", "unused")
    monkeypatch.setenv("APPLE_REDIRECT_URI", "http://testserver/auth/apple/callback")

    from app.api.oauth_apple import router as apple_router

    app = FastAPI()
    app.include_router(apple_router, prefix="")
    client = TestClient(app, follow_redirects=False)
    return client


def test_apple_callback_sets_cookies_on_returned_302(monkeypatch):
    client = _make_client(monkeypatch)

    # Craft a minimal form payload; the route will attempt network unless we stub httpx.
    # Stub httpx exchange by monkeypatching the handler to short-circuit before network.
    import app.api.oauth_apple as oa
    class _FakeClient:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return False
        async def post(self, url, data=None, **kwargs):
            class _R:
                status_code = 200
                def json(self):
                    return {"id_token": "eyJhbGciOiAiRVMyNTYifQ.eyJzdWIiOiAidXNlckBleGFtcGxlLmNvbSJ9.sig"}
            return _R()
    oa.httpx.AsyncClient = lambda timeout=10: _FakeClient()  # type: ignore
    # Stub signer to avoid ES256 private key handling during tests
    oa._sign_client_secret = lambda team_id, client_id, key_id, private_key: "fake"  # type: ignore

    # Now call the callback with minimal fields
    r = client.post(
        "/auth/apple/callback",
        data={"code": "x", "state": "/"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert r.status_code in (302, 307)
    # Ensure cookies are present on the response we returned
    cookie_header = ",".join(r.cookies.keys()) if getattr(r, "cookies", None) else ";".join(r.headers.get("set-cookie", "").split("\n"))
    # We expect Set-Cookie headers for access_token and refresh_token
    assert "access_token" in (r.headers.get("set-cookie") or "")
    assert "refresh_token" in (r.headers.get("set-cookie") or "")


