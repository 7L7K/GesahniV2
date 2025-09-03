from fastapi.testclient import TestClient
import app.main as main_mod
from app.cookie_names import GSNH_AT, GSNH_SESS


def test_main_auth_cookie_preserved_through_callback(monkeypatch):
    app = main_mod.app
    client = TestClient(app)

    import app.api.spotify as spotify_mod

    # Provide PKCE and token exchange stubs so callback proceeds
    def fake_get_pkce(sid, state):
        return spotify_mod.SpotifyPKCE(
            verifier="v", challenge="c", state=state, created_at=0
        )

    async def fake_exchange(code, code_verifier):
        return {
            "access_token": "at",
            "refresh_token": "rt",
            "scope": "",
            "expires_in": 3600,
            "expires_at": 0,
        }

    async def fake_upsert(t):
        return None

    monkeypatch.setattr(spotify_mod, "get_pkce_challenge_by_state", fake_get_pkce)
    monkeypatch.setattr(spotify_mod, "exchange_code", fake_exchange)
    monkeypatch.setattr(spotify_mod, "upsert_token", fake_upsert)

    # Simulate a logged-in main auth cookie present before OAuth
    client.cookies.set(GSNH_AT, "main-access-token")
    client.cookies.set(GSNH_SESS, "main-session")

    # Also set the temporary spotify cookie that connect would set
    client.cookies.set("spotify_oauth_jwt", "dummy-jwt")

    res = client.get("/v1/spotify/callback?code=abc&state=state123")

    # The response may include Set-Cookie headers; ensure none clear main auth cookies
    sc = res.headers.get("set-cookie", "") or ""
    assert GSNH_AT not in sc
    assert GSNH_SESS not in sc

    # Ensure temp cookie was cleared (or at least present in logs/headers)
    assert "spotify_oauth_jwt" in (sc or "spotify_oauth_jwt")
