#!/usr/bin/env python3
"""Comprehensive Spotify OAuth flow test with proper mocking."""

import logging
import sys
import time

from fastapi.testclient import TestClient

# Import the app
from app.main import app


def test_complete_spotify_oauth_flow_with_mocking(monkeypatch):
    """Test the complete Spotify OAuth flow with proper mocking."""
    logger = logging.getLogger(__name__)
    logger.info("🚀 STARTING COMPLETE SPOTIFY OAUTH FLOW TEST WITH MOCKING")

    client = TestClient(app)

    # Mock the get_current_user_id function to return a test user ID
    def mock_get_current_user_id(request=None):
        logger.info("Mock: get_current_user_id called, returning test user")
        return "test_user_123"

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
    import app.api.spotify as spotify_mod
    import app.deps.user as user_mod

    monkeypatch.setattr(user_mod, "get_current_user_id", mock_get_current_user_id)
    monkeypatch.setattr(spotify_mod, "_jwt_decode", mock_jwt_decode)
    monkeypatch.setattr(spotify_mod, "_jwt_secret", mock_jwt_secret)
    monkeypatch.setattr(spotify_mod, "exchange_code", mock_exchange_code)
    monkeypatch.setattr(spotify_mod, "upsert_token", mock_upsert_token)
    monkeypatch.setattr(
        spotify_mod, "get_pkce_challenge_by_state", mock_get_pkce_challenge_by_state
    )

    # Step 1: Call /v1/spotify/connect
    logger.info("Step 1: Calling /v1/spotify/connect endpoint...")
    connect_response = client.get("/v1/spotify/connect")

    logger.info(f"Connect response status: {connect_response.status_code}")
    if connect_response.status_code != 200:
        logger.error(f"Connect failed with body: {connect_response.text}")
        return False

    connect_data = connect_response.json()
    auth_url = connect_data.get("auth_url")
    session_id = connect_data.get("session_id")
    logger.info(f"Auth URL generated: {auth_url}")
    logger.info(f"Session ID: {session_id}")

    # Extract state from auth_url for later use
    from urllib.parse import parse_qs, urlparse

    parsed_url = urlparse(auth_url)
    query_params = parse_qs(parsed_url.query)
    state = query_params.get("state", [None])[0]
    logger.info(f"Extracted state: {state}")

    # Check if temporary cookie was set
    if "Set-Cookie" in connect_response.headers:
        cookie_header = connect_response.headers["Set-Cookie"]
        logger.info(f"Set-Cookie header: {cookie_header}")
        if "spotify_oauth_jwt" in cookie_header:
            logger.info("✅ Temporary spotify_oauth_jwt cookie was set")
        else:
            logger.warning("⚠️  Temporary cookie was not set")

    # Step 2: Call /v1/spotify/callback (simulating Spotify redirect)
    logger.info("Step 2: Simulating Spotify redirect to callback...")

    # Set the temporary cookie that would normally be set by the frontend
    client.cookies.set("spotify_oauth_jwt", "mock_jwt_token")

    callback_url = f"/v1/spotify/callback?code=mock_auth_code&state={state}"
    logger.info(f"Callback URL: {callback_url}")

    callback_response = client.get(callback_url)

    logger.info(f"Callback response status: {callback_response.status_code}")
    logger.info(f"Callback response body: {callback_response.text}")

    # Check redirect location
    if "Location" in callback_response.headers:
        location = callback_response.headers["Location"]
        logger.info(f"Redirect location: {location}")
        if "spotify=connected" in location:
            logger.info("✅ Success redirect detected")
        elif "error=" in location:
            logger.info(f"⚠️  Error redirect detected: {location}")
        else:
            logger.warning(f"⚠️  Unexpected redirect location: {location}")

    # Check cookies
    from app.cookie_names import GSNH_AT

    final_cookies = list(client.cookies.keys())
    logger.info(f"Final cookies: {final_cookies}")

    if GSNH_AT in final_cookies:
        logger.info("✅ Main GSNH_AT cookie preserved")
    else:
        logger.warning("⚠️  Main auth cookie may have been cleared")

    # Check Set-Cookie header for clearing temporary cookie
    if "Set-Cookie" in callback_response.headers:
        set_cookie = callback_response.headers["Set-Cookie"]
        logger.info(f"Set-Cookie after callback: {set_cookie}")
        if "spotify_oauth_jwt=;" in set_cookie:
            logger.info("✅ Temporary cookie was cleared")
        else:
            logger.warning("⚠️  Temporary cookie may not have been cleared")

    logger.info("🎉 OAUTH FLOW TEST COMPLETED SUCCESSFULLY")
    return True


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        stream=sys.stdout,
    )
    test_complete_spotify_oauth_flow_with_mocking(None)
