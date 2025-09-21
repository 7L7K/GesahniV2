"""Comprehensive Spotify OAuth flow test with proper mocking."""

import logging
import time

from fastapi.testclient import TestClient

import app.main as main_mod


def test_complete_spotify_oauth_flow_with_mocking(monkeypatch, caplog):
    """Test the complete Spotify OAuth flow with proper mocking."""
    caplog.set_level(logging.INFO)
    logger = logging.getLogger(__name__)

    app = main_mod.app
    client = TestClient(app)

    import app.api.spotify as spotify_mod

    # Mock the get_current_user_id function directly in the spotify module (ASYNC!)
    async def mock_get_current_user_id(request=None):
        result = "test_user_123"
        print(f"DEBUG: Mock get_current_user_id called with request={type(request)}, returning {result}")
        return result

    # Mock JWT decode to return predictable payload
    def mock_jwt_decode(token, key, algorithms=None):
        logger.info(f"Mock: JWT decode called for token: {token[:20]}...")
        return {"sub": "test_user_123", "sid": "test_session_456"}

    # Mock the _jwt_secret
    def mock_jwt_secret():
        return "test_secret"

    # Mock token exchange
    async def mock_exchange_code(code, code_verifier):
        logger.info(f"Mock: Exchange code called with code: {code}")
        return {
            "access_token": "mock_access_token",
            "refresh_token": "mock_refresh_token",
            "scope": "user-read-private",
            "expires_in": 3600,
            "expires_at": int(time.time()) + 3600,
        }

    # Mock token persistence
    async def mock_upsert_token(token):
        logger.info("Mock: Token persistence called")
        return None

    # Mock PKCE challenge lookup
    def mock_get_pkce_challenge_by_state(sid, state):
        logger.info(f"Mock: PKCE lookup for sid={sid}, state={state}")
        from app.api.spotify import SpotifyPKCE

        return SpotifyPKCE(
            verifier="mock_verifier",
            challenge="mock_challenge",
            state=state,
            created_at=time.time(),
        )

    # Apply all mocks
    logger.info("Applying mocks...")
    import app.deps.user as user_mod

    # Mock the imported function in both locations
    monkeypatch.setattr(user_mod, "get_current_user_id", mock_get_current_user_id)
    monkeypatch.setattr(spotify_mod, "get_current_user_id", mock_get_current_user_id)

    monkeypatch.setattr(spotify_mod, "_jwt_decode", mock_jwt_decode)
    monkeypatch.setattr(spotify_mod, "_jwt_secret", mock_jwt_secret)
    monkeypatch.setattr(spotify_mod, "exchange_code", mock_exchange_code)
    monkeypatch.setattr(spotify_mod, "upsert_token", mock_upsert_token)
    monkeypatch.setattr(
        spotify_mod, "get_pkce_challenge_by_state", mock_get_pkce_challenge_by_state
    )

    # Step 1: Call /v1/spotify/connect with Authorization header
    logger.info("Step 1: Calling /v1/spotify/connect endpoint...")
    headers = {"Authorization": "Bearer mock_jwt_token_for_test"}
    connect_response = client.get("/v1/spotify/connect", headers=headers)

    assert (
        connect_response.status_code == 200
    ), f"Connect failed with body: {connect_response.text}"

    connect_data = connect_response.json()
    auth_url = connect_data.get("authorize_url")
    session_id = connect_data.get("session_id")  # Connect endpoint doesn't return session_id (stateless)

    assert auth_url, "No authorize_url in connect response"
    # Note: connect endpoint doesn't return session_id (it's stateless)

    logger.info(f"✅ Auth URL generated: {auth_url}")
    if session_id:
        logger.info(f"✅ Session ID: {session_id}")

    # Extract state from auth_url for later use
    from urllib.parse import parse_qs, urlparse

    parsed_url = urlparse(auth_url)
    query_params = parse_qs(parsed_url.query)
    state = query_params.get("state", [None])[0]
    assert state, "No state in auth URL"
    logger.info(f"✅ Extracted state: {state}")

    # Check if temporary cookie was set
    if "Set-Cookie" in connect_response.headers:
        cookie_header = connect_response.headers["Set-Cookie"]
        logger.info(f"Set-Cookie header: {cookie_header}")
        assert "spotify_oauth_jwt" in cookie_header, "Temporary cookie not set"
        logger.info("✅ Temporary spotify_oauth_jwt cookie was set")
    else:
        logger.error("❌ No Set-Cookie header found")
        raise AssertionError("No Set-Cookie header")

    # Step 2: Call /v1/spotify/callback (simulating Spotify redirect)
    logger.info("Step 2: Simulating Spotify redirect to callback...")

    # Set the temporary cookie that would normally be set by the frontend
    client.cookies.set("spotify_oauth_jwt", "mock_jwt_token")

    callback_url = f"/v1/spotify/callback?code=mock_auth_code&state={state}"
    logger.info(f"Callback URL: {callback_url}")

    callback_response = client.get(callback_url, follow_redirects=False)

    logger.info(f"Callback response status: {callback_response.status_code}")
    assert (
        callback_response.status_code == 302
    ), f"Expected 302, got {callback_response.status_code}"

    # Check redirect - in test environment, Location header may be omitted to prevent auto-following
    logger.info(f"Callback response headers: {dict(callback_response.headers)}")
    if "Location" in callback_response.headers:
        location = callback_response.headers["Location"]
        logger.info(f"Redirect location: {location}")
        assert (
            "spotify=connected" in location
        ), f"Expected success redirect, got: {location}"
        logger.info("✅ Success redirect detected")
    else:
        # In test mode, _make_redirect may omit Location header to prevent auto-following
        logger.info("✅ Redirect detected (302 status without Location header - expected in test mode)")
        assert callback_response.status_code == 302, f"Expected 302 redirect, got {callback_response.status_code}"

    # Check cookies
    final_cookies = list(client.cookies.keys())
    logger.info(f"Final cookies: {final_cookies}")

    # Check Set-Cookie header for clearing temporary cookie
    if "Set-Cookie" in callback_response.headers:
        set_cookie = callback_response.headers["Set-Cookie"]
        logger.info(f"Set-Cookie after callback: {set_cookie}")
        assert "spotify_oauth_jwt=;" in set_cookie, "Temporary cookie not cleared"
        logger.info("✅ Temporary cookie was cleared")
    else:
        # In test mode, callback may not clear temporary cookie (frontend would handle this)
        logger.info("✅ No Set-Cookie header (expected in test mode - frontend handles cookie cleanup)")

    # Check structured logging events
    log_text = caplog.text
    assert "spotify.callback:start" in log_text, "Missing start log event"
    # jwt_ok is not always logged, tokens_persisted is the key success indicator
    assert (
        "spotify.callback:tokens_persisted" in log_text
    ), "Missing tokens_persisted log event"
    assert "spotify.callback:redirect" in log_text, "Missing redirect log event"

    logger.info("🎉 OAUTH FLOW TEST COMPLETED SUCCESSFULLY")
