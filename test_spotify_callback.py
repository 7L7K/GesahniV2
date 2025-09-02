#!/usr/bin/env python3
"""
Test script for Spotify OAuth callback with proper transaction storage.
"""

import sys
import os
import requests
import json
import jwt
import time
import uuid
import secrets

# Add the app directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '.'))

from app.api.oauth_store import put_tx

def test_spotify_callback():
    """Test the Spotify callback with proper transaction setup."""

    # Generate transaction data
    tx_id = uuid.uuid4().hex
    user_id = 'testuser'

    # Create JWT state
    secret = os.getenv('JWT_SECRET', 'dev_jwt_secret_key_for_testing_only')
    state_payload = {
        "tx": tx_id,
        "uid": user_id,
        "exp": int(time.time()) + 600,  # 10 minutes
        "iat": int(time.time()),
    }

    state = jwt.encode(state_payload, secret, algorithm="HS256")

    # Store transaction data
    tx_data = {
        "user_id": user_id,
        "code_verifier": f"test_verifier_{secrets.token_hex(16)}",
        "ts": int(time.time())
    }

    print(f"Storing transaction data for tx_id: {tx_id}")
    put_tx(tx_id, tx_data, ttl_seconds=600)

    # Now make the callback request
    callback_url = "http://127.0.0.1:8000/v1/spotify/callback"
    params = {
        "code": "fake",
        "state": state
    }

    print(f"Making callback request with state: {state[:50]}...")
    try:
        response = requests.get(callback_url, params=params, timeout=10)
        print(f"Response status: {response.status_code}")
        print(f"Response content: {response.text[:200]}...")
    except Exception as e:
        print(f"Request failed: {e}")

if __name__ == "__main__":
    test_spotify_callback()
