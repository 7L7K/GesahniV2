import time
import logging
from fastapi.testclient import TestClient

import app.main as main_mod


def test_callback_oauth_error_redirects(monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    app = main_mod.app
    client = TestClient(app)

    client.get("/v1/spotify/callback?error=access_denied&error_description=denied")
    # Should prepare redirect (we log a redirect event)
    assert "spotify.callback:redirect" in caplog.text
    assert "OAuth error from Spotify" in caplog.text


def test_callback_invalid_pkce_redirects(monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    app = main_mod.app
    client = TestClient(app)

    import app.api.spotify as spotify_mod

    def fake_jwt_decode(token, key, algorithms=None):
        return {"sub": "u_x", "sid": "s_x"}

    # Make PKCE lookup return None
    monkeypatch.setattr(spotify_mod, "_jwt_decode", fake_jwt_decode)
    monkeypatch.setattr(
        spotify_mod, "get_pkce_challenge_by_state", lambda sid, state: None
    )

    from app.cookie_names import GSNH_AT

    client.get("/v1/spotify/callback?code=abc&state=stateX", cookies={GSNH_AT: "t"})
    assert "spotify.callback:redirect" in caplog.text
    assert "Invalid session/state - no matching PKCE found" in caplog.text


def test_callback_token_exchange_failure(monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    app = main_mod.app
    client = TestClient(app)

    import app.api.spotify as spotify_mod

    def fake_jwt_decode(token, key, algorithms=None):
        return {"sub": "u_err", "sid": "s_err"}

    def fake_get_pkce_challenge_by_state(sid, state):
        return spotify_mod.SpotifyPKCE(
            verifier="ver", challenge="ch", state=state, created_at=time.time()
        )

    async def bad_exchange(code, code_verifier):
        raise RuntimeError("upstream error")

    monkeypatch.setattr(spotify_mod, "_jwt_decode", fake_jwt_decode)
    monkeypatch.setattr(
        spotify_mod, "get_pkce_challenge_by_state", fake_get_pkce_challenge_by_state
    )
    monkeypatch.setattr(spotify_mod, "exchange_code", bad_exchange)

    from app.cookie_names import GSNH_AT

    client.get("/v1/spotify/callback?code=abc&state=stateX", cookies={GSNH_AT: "t"})
    assert "spotify.callback:redirect" in caplog.text
    assert "Token exchange or persistence failed" in caplog.text
