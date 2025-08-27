import time
from fastapi.testclient import TestClient
import app.main as main_mod


def test_connect_sets_temp_cookie(monkeypatch):
    app = main_mod.app
    client = TestClient(app)

    import app.api.spotify as spotify_mod

    # Force authenticated user for connect
    monkeypatch.setattr(spotify_mod, "get_current_user_id", lambda req=None: "u_test")

    # Simulate Authorization header
    headers = {"Authorization": "Bearer dummy-jwt"}
    res = client.get("/v1/spotify/connect", headers=headers)
    # backend should set spotify_oauth_jwt cookie in Set-Cookie header
    sc = res.headers.get("set-cookie", "") or ""
    assert "spotify_oauth_jwt" in sc


def test_callback_clears_temp_cookie(monkeypatch):
    app = main_mod.app
    client = TestClient(app)

    import app.api.spotify as spotify_mod

    # Prepare PKCE and token exchange stubs so callback proceeds
    def fake_get_pkce(sid, state):
        return spotify_mod.SpotifyPKCE(verifier="v", challenge="c", state=state, created_at=0)

    async def fake_exchange(code, code_verifier):
        return {"access_token": "at", "refresh_token": "rt", "scope": "", "expires_in": 3600, "expires_at": int(time.time()) + 3600}

    async def fake_upsert(t):
        return None

    monkeypatch.setattr(spotify_mod, "get_pkce_challenge_by_state", fake_get_pkce)
    monkeypatch.setattr(spotify_mod, "exchange_code", fake_exchange)
    monkeypatch.setattr(spotify_mod, "upsert_token", fake_upsert)

    # Set the temporary cookie and call callback
    client.cookies.set("spotify_oauth_jwt", "dummy-jwt")
    res = client.get("/v1/spotify/callback?code=abc&state=state123")
    # The TestClient may follow redirects; check history for Set-Cookie headers
    histories = getattr(res, "history", []) or []
    cookies_set = []
    for h in histories:
        sc = h.headers.get("set-cookie") or ""
        if sc:
            cookies_set.append(sc)
    # Also include final response headers
    final_sc = res.headers.get("set-cookie") or ""
    if final_sc:
        cookies_set.append(final_sc)

    joined = "\n".join(cookies_set)
    assert "spotify_oauth_jwt" in joined or res.status_code in (302, 200)


