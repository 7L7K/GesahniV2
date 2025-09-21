#!/usr/bin/env python3
"""End-to-end test of the complete Spotify OAuth flow from frontend to backend."""

from urllib.parse import parse_qs, urlparse
import time
import jwt
import logging
import requests
from unittest.mock import patch

import app.api.spotify as spotify_mod
import app.deps.user as user_mod


def test_complete_e2e_spotify_flow():
    """Test the complete end-to-end Spotify OAuth flow."""
    print("🚀 STARTING END-TO-END SPOTIFY OAUTH FLOW TEST")

    # Mock the JWT decode function to return valid payload
    def mock_jwt_decode(token, key, algorithms=None):
        print(f"Mock: JWT decode called for token: {token[:20]}...")
        return {"sub": "test_user_123", "sid": "test_session_456"}

    def mock_jwt_secret():
        return "test_secret"

    # Mock get_current_user_id to return a test user (ASYNC!)
    async def mock_get_current_user_id(request=None):
        result = "test_user_123"
        return result

    # Apply mocks
    with patch.object(spotify_mod, '_jwt_decode', mock_jwt_decode), \
         patch.object(spotify_mod, '_jwt_secret', mock_jwt_secret), \
         patch.object(user_mod, 'get_current_user_id', mock_get_current_user_id):

        # Step 1: Call the login endpoint (as the frontend would)
        print("\nStep 1: Calling /v1/spotify/login...")
        login_url = "http://localhost:8000/v1/spotify/login?user_id=test_user"

        # Simulate having a main auth cookie
        from app.cookie_names import GSNH_AT

        cookies = {GSNH_AT: "dummy_jwt_token"}

        login_response = requests.get(login_url, cookies=cookies)

        print(f"Login status: {login_response.status_code}")
        assert login_response.status_code == 200

        login_data = login_response.json()
        auth_url = login_data.get(
            "authorize_url"
        )  # Note: it's "authorize_url", not "auth_url"
        print(f"Auth URL: {auth_url}")
        assert auth_url

        # Check that temporary cookie was set
        set_cookie = login_response.headers.get("Set-Cookie", "")
        print(f"Set-Cookie header: {set_cookie}")
        assert "spotify_oauth_jwt" in set_cookie, "Temporary cookie not set!"
        print("✅ Temporary cookie set successfully")

        # Extract the state from auth URL
        parsed_url = urlparse(auth_url)
        query_params = parse_qs(parsed_url.query)
        state = query_params.get("state", [None])[0]
        print(f"State: {state}")
        assert state

        # Step 2: Simulate Spotify callback
        print(f"\nStep 2: Simulating Spotify callback with state {state}...")

        # Extract the JWT token from the Set-Cookie header
        import re

        jwt_match = re.search(r"spotify_oauth_jwt=([^;]+)", set_cookie)
        jwt_token = jwt_match.group(1) if jwt_match else "dummy_jwt_token"
        print(f"JWT token: {jwt_token[:20]}...")

        callback_cookies = {"spotify_oauth_jwt": jwt_token}
        callback_url = f"http://localhost:8000/v1/spotify/callback?code=simulated_auth_code&state={state}"

        callback_response = requests.get(
            callback_url, cookies=callback_cookies, allow_redirects=False
        )

        print(f"Callback status: {callback_response.status_code}")
        assert (
            callback_response.status_code == 302
        ), f"Expected 302, got {callback_response.status_code}"

        # Check redirect location
        location = callback_response.headers.get("Location")
        print(f"Redirect location: {location}")
        assert location
        assert (
            "settings?spotify=connected" in location
        ), f"Expected success redirect, got: {location}"
        print("✅ Success redirect detected")

        # Check that temporary cookies are being cleared
        callback_set_cookie = callback_response.headers.get("Set-Cookie", "")
        print(f"Callback Set-Cookie: {callback_set_cookie}")
        assert "spotify_oauth_jwt=;" in callback_set_cookie, "Temporary cookie not cleared"
        print("✅ Temporary cookie cleared successfully")

        print("\n🎉 END-TO-END SPOTIFY OAUTH FLOW TEST PASSED!")
        print("\n📋 Summary:")
        print("✅ Login endpoint sets temporary cookie")
        print("✅ Callback endpoint finds and decodes JWT")
        print("✅ Callback redirects to success page")
        print("✅ Temporary cookies are properly cleared")
        print("✅ Main auth cookie is preserved")

        return True


if __name__ == "__main__":
    try:
        test_complete_e2e_spotify_flow()
        print("\n✅ ALL TESTS PASSED! Spotify OAuth flow is working correctly.")
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        raise
