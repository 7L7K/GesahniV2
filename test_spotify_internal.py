#!/usr/bin/env python3
"""
Test script that calls Spotify callback internally.
"""

import sys
import os
import asyncio
import jwt
import time
from unittest.mock import Mock

# Set test mode
os.environ["SPOTIFY_TEST_MODE"] = "1"

# Add the app directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '.'))

from app.api.spotify import spotify_callback
from starlette.requests import Request
from starlette.responses import Response

async def test_callback_internal():
    """Test the Spotify callback internally."""

    # Create a simple JWT state
    tx_id = 'internal_test_tx'
    user_id = 'testuser'
    secret = os.getenv('JWT_SECRET', 'dev_jwt_secret_key_for_testing_only')

    payload = {
        'tx': tx_id,
        'uid': user_id,
        'exp': int(time.time()) + 600,
        'iat': int(time.time()),
    }

    state = jwt.encode(payload, secret, algorithm="HS256")

    # Create a mock request
    mock_request = Mock(spec=Request)
    mock_request.method = "GET"
    mock_request.url = Mock()
    mock_request.url.scheme = "http"
    mock_request.url.host = "127.0.0.1"
    mock_request.url.port = 8000
    mock_request.url.path = "/v1/spotify/callback"
    mock_request.headers = {
        "host": "127.0.0.1:8000",
        "user-agent": "test-script",
        "accept": "*/*"
    }
    mock_request.client = Mock()
    mock_request.client.host = "127.0.0.1"

    print(f"Testing callback with state: {state[:50]}...")

    # Call the callback function directly
    print(f"Calling callback with code='fake', state='{state[:50]}...'")
    response = await spotify_callback(
        request=mock_request,
        code="fake",
        state=state
    )

    print(f"Response type: {type(response)}")
    if hasattr(response, 'status_code'):
        print(f"Response status: {response.status_code}")
    if hasattr(response, 'body'):
        print(f"Response body length: {len(response.body)}")

    return response

if __name__ == "__main__":
    asyncio.run(test_callback_internal())
