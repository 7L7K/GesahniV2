import logging
import time

from fastapi.testclient import TestClient

import app.main as main_mod


def test_callback_oauth_error_redirects(monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    app = main_mod.app
    client = TestClient(app)

    print("DEBUG: Making callback request with error params")
    res = client.get("/v1/spotify/callback?error=access_denied&error_description=denied")
    print(f"DEBUG: Response status: {res.status_code}")
    # Should prepare redirect (we log a redirect event)
    print(f"DEBUG: Caplog text length: {len(caplog.text)}")
    print(f"DEBUG: Caplog text content: {repr(caplog.text)}")
    print(f"DEBUG: Looking for 'spotify.callback:redirect' in caplog: {'spotify.callback:redirect' in caplog.text}")
    print(f"DEBUG: Looking for 'OAuth error' in caplog: {'OAuth error' in caplog.text}")

    assert res.status_code == 302  # Should get 302 redirect
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

    print("DEBUG: Making callback request with invalid PKCE")
    res = client.get("/v1/spotify/callback?code=abc&state=stateX", cookies={GSNH_AT: "t"})
    print(f"DEBUG: Response status: {res.status_code}")
    print(f"DEBUG: Caplog text length: {len(caplog.text)}")
    print(f"DEBUG: Caplog text content: {repr(caplog.text)}")
    print(f"DEBUG: Looking for 'spotify.callback:redirect' in caplog: {'spotify.callback:redirect' in caplog.text}")
    print(f"DEBUG: Looking for 'Invalid session' in caplog: {'Invalid session' in caplog.text}")

    # Check if the redirect happened (status code 302)
    assert res.status_code == 302  # Should get 302 redirect

    # Check if the log message was captured
    if "spotify.callback:redirect" not in caplog.text:
        print(f"ERROR: 'spotify.callback:redirect' not found in caplog.text")
        spotify_lines = [line for line in caplog.text.split('\n') if 'spotify' in line]
        print(f"ERROR: Available spotify log messages: {spotify_lines}")

    assert "spotify.callback:redirect" in caplog.text
    assert "Token exchange failed" in caplog.text


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

    print("DEBUG: Making callback request with token exchange failure")
    res = client.get("/v1/spotify/callback?code=abc&state=stateX", cookies={GSNH_AT: "t"})
    print(f"DEBUG: Response status: {res.status_code}")
    print(f"DEBUG: Caplog text length: {len(caplog.text)}")
    print(f"DEBUG: Caplog text content: {repr(caplog.text)}")
    print(f"DEBUG: Looking for 'spotify.callback:redirect' in caplog: {'spotify.callback:redirect' in caplog.text}")
    print(f"DEBUG: Looking for 'Token exchange' in caplog: {'Token exchange' in caplog.text}")

    assert res.status_code == 302  # Should get 302 redirect
    assert "spotify.callback:redirect" in caplog.text
    assert "Token exchange failed" in caplog.text  # This test also gets token exchange failure
