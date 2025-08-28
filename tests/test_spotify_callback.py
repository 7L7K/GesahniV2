import time
from fastapi.testclient import TestClient

import app.main as main_mod


def test_callback_success_flow(monkeypatch, caplog):
    app = main_mod.app
    client = TestClient(app)

    # Monkeypatch JWT decode to return a predictable payload
    import app.api.spotify as spotify_mod

    async def fake_exchange_code(code, code_verifier):
        return {
            "access_token": "at-1",
            "refresh_token": "rt-1",
            "scope": "user-read-private",
            "expires_in": 3600,
            "expires_at": int(time.time()) + 3600,
        }

    def fake_get_pkce_challenge_by_state(sid, state):
        # Use the real SpotifyPKCE class if available
        try:
            return spotify_mod.SpotifyPKCE(verifier="ver", challenge="ch", state=state, created_at=time.time())
        except Exception:
            # Minimal fallback object
            return type("P", (), {"verifier": "ver", "created_at": time.time()})()

    async def fake_upsert_token(token):
        # noop: pretend to persist
        return None

    def fake_jwt_decode(token, key, algorithms=None):
        return {"sub": "u_123", "sid": "s_456"}

    monkeypatch.setattr(spotify_mod, "_jwt_decode", fake_jwt_decode)
    monkeypatch.setattr(spotify_mod, "get_pkce_challenge_by_state", fake_get_pkce_challenge_by_state)
    monkeypatch.setattr(spotify_mod, "exchange_code", fake_exchange_code)
    monkeypatch.setattr(spotify_mod, "upsert_token", fake_upsert_token)

    # Make the callback request with cookie set (as connect would)
    from app.cookie_names import GSNH_AT
    cookies = {GSNH_AT: "dummy-token"}
    res = client.get("/v1/spotify/callback?code=abc&state=state123", cookies=cookies)

    # Expect initial redirect to connected (TestClient may follow it). Check history
    histories = getattr(res, "history", []) or []
    assert any("/settings?spotify=connected" in (h.headers.get("Location") or "") for h in histories) or "/settings?spotify=connected" in (res.headers.get("Location") or "")

    # Check logging order: start -> jwt_ok -> tokens_persisted
    text = caplog.text
    idx_start = text.find("spotify.callback:start")
    idx_jwt = text.find("spotify.callback:jwt_ok")
    idx_tokens = text.find("spotify.callback:tokens_persisted")

    assert idx_start != -1 and idx_jwt != -1 and idx_tokens != -1
    assert idx_start < idx_jwt < idx_tokens


def test_callback_no_cookie_redirects_no_session(monkeypatch, caplog):
    app = main_mod.app
    client = TestClient(app)

    import app.api.spotify as spotify_mod

    # Ensure JWT decode won't be called — simulate missing token
    monkeypatch.setattr(spotify_mod, "_jwt_decode", lambda *a, **k: {"sub": "unknown"})

    # The TestClient may follow redirects; assert via logs that error was handled
    client.get("/v1/spotify/callback?code=abc&state=state123")
    assert "No valid session identifier" in caplog.text


def test_callback_missing_code_redirects_no_code(monkeypatch, caplog):
    app = main_mod.app
    client = TestClient(app)

    import app.api.spotify as spotify_mod

    # Provide a valid JWT so sid resolves, and ensure pkce is present
    def fake_jwt_decode(token, key, algorithms=None):
        return {"sub": "u_789", "sid": "s_789"}

    def fake_get_pkce_challenge_by_state(sid, state):
        return spotify_mod.SpotifyPKCE(verifier="ver", challenge="ch", state=state, created_at=time.time())

    monkeypatch.setattr(spotify_mod, "_jwt_decode", fake_jwt_decode)
    monkeypatch.setattr(spotify_mod, "get_pkce_challenge_by_state", fake_get_pkce_challenge_by_state)

    from app.cookie_names import GSNH_AT
    client.get("/v1/spotify/callback?state=state123", cookies={GSNH_AT: "t"})
    assert "Missing authorization code" in caplog.text


