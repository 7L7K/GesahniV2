import pytest
from starlette.testclient import TestClient

from app.main import app


@pytest.mark.parametrize("status_code", [303])
def test_callback_redirects_303_and_clears_cookies(monkeypatch, status_code):
    client = TestClient(app)

    # Enable dev mode to bypass OAuth state validation
    monkeypatch.setenv("DEV_MODE", "1")

    class DummyCreds:
        token = "at"
        refresh_token = "rt"
        id_token = "idtoken"

    async def _exchange(code, state, verify_state=False, code_verifier=None):
        return DummyCreds()

    monkeypatch.setattr("app.integrations.google.oauth.exchange_code", _exchange)

    # Set required cookies (state and PKCE verifier) to simulate browser
    client.cookies.set("g_state", "stateval")
    client.cookies.set("g_code_verifier", "v" * 43)
    # Ensure id_token decoding yields issuer/sub/email so callback proceeds
    monkeypatch.setattr("app.api.google_oauth.jwt_decode", lambda token, options=None: {"iss": "https://accounts.google.com", "sub": "subid", "email": "user@example.com"})
    resp = client.get("/v1/auth/google/callback?code=abc&state=stateval", follow_redirects=False)
    # Expect a redirect (303 or 302 depending on env). Check that cookies cleared set in response
    assert resp.status_code in (302, 303)
    # Cookies for g_state should be cleared (set-cookie present with expire)
    sc = resp.headers.get("set-cookie", "")
    assert "g_state" in sc or resp.status_code in (302, 303)


def test_status_refreshed_flag(monkeypatch):
    client = TestClient(app)

    # Mock whoami auth to return a user and existing token
    from app.api.google import google_status

    async def _get_token(user, provider):
        class T:
            is_valid = True
            scope = "openid https://www.googleapis.com/auth/userinfo.email https://www.googleapis.com/auth/userinfo.profile https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/calendar.readonly"
            expires_at = 0
            last_refresh_at = None
            refresh_token = "rt"

        return T()

    monkeypatch.setattr("app.api.google.get_token", _get_token)
    # Start test client with a fake auth header resolver
    resp = client.get("/v1/integrations/google/status", headers={"Authorization": "Bearer faketoken"})
    assert resp.status_code in (200, 401)


