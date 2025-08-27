#!/usr/bin/env python3
"""Comprehensive Spotify OAuth flow test with detailed logging."""

import time
import logging
import sys
from fastapi.testclient import TestClient

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

# Import the app
from app.main import app

def test_complete_spotify_oauth_flow():
    """Test the complete Spotify OAuth flow with detailed logging."""
    logger.info("🚀 STARTING COMPLETE SPOTIFY OAUTH FLOW TEST")

    client = TestClient(app)

    # Step 1: Simulate user login and get JWT
    logger.info("Step 1: Simulating user login and JWT generation...")
    # In a real test, you'd authenticate properly, but for now we'll simulate
    jwt_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1XzEyMyIsInNpZCI6InNfNDU2IiwiaWF0IjoxNjcwMDAwMDAwLCJleHAiOjE2NzAwMDAzNjB9.test"

    # Step 2: Call /v1/spotify/connect
    logger.info("Step 2: Calling /v1/spotify/connect endpoint...")
    connect_headers = {"Authorization": f"Bearer {jwt_token}"}
    connect_response = client.get("/v1/spotify/connect", headers=connect_headers)

    logger.info(f"Connect response status: {connect_response.status_code}")
    logger.info(f"Connect response headers: {dict(connect_response.headers)}")
    logger.info(f"Connect response body: {connect_response.text}")

    if connect_response.status_code != 200:
        logger.error("Connect failed!")
        return False

    connect_data = connect_response.json()
    auth_url = connect_data.get("auth_url")
    logger.info(f"Auth URL generated: {auth_url}")

    # Extract state from auth_url for later use
    from urllib.parse import urlparse, parse_qs
    parsed_url = urlparse(auth_url)
    query_params = parse_qs(parsed_url.query)
    state = query_params.get('state', [None])[0]
    logger.info(f"Extracted state: {state}")

    # Check if temporary cookie was set
    if "Set-Cookie" in connect_response.headers:
        cookie_header = connect_response.headers["Set-Cookie"]
        logger.info(f"Set-Cookie header: {cookie_header}")
        if "spotify_oauth_jwt" in cookie_header:
            logger.info("✅ Temporary spotify_oauth_jwt cookie was set")
        else:
            logger.warning("⚠️  Temporary cookie was not set")

    # Step 3: Simulate Spotify redirect to callback
    logger.info("Step 3: Simulating Spotify redirect to callback...")
    logger.info(f"Using state: {state}")

    # First set the temporary cookie on the client (as if the frontend had it)
    client.cookies.set("spotify_oauth_jwt", jwt_token)

    # Now call the callback endpoint
    callback_url = f"/v1/spotify/callback?code=abc123&state={state}"
    logger.info(f"Callback URL: {callback_url}")

    callback_response = client.get(callback_url)

    logger.info(f"Callback response status: {callback_response.status_code}")
    logger.info(f"Callback response headers: {dict(callback_response.headers)}")
    logger.info(f"Callback response body: {callback_response.text}")

    # Check redirect location
    if "Location" in callback_response.headers:
        location = callback_response.headers["Location"]
        logger.info(f"Redirect location: {location}")
        if "spotify=connected" in location:
            logger.info("✅ Success redirect detected")
        else:
            logger.warning(f"⚠️  Unexpected redirect location: {location}")

    # Check if main auth cookie is still present
    main_cookies = list(client.cookies.keys())
    logger.info(f"Cookies after callback: {main_cookies}")

    if "auth_token" in main_cookies:
        logger.info("✅ Main auth_token cookie preserved")
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

    logger.info("🎉 OAUTH FLOW TEST COMPLETED")
    return True

if __name__ == "__main__":
    test_complete_spotify_oauth_flow()
