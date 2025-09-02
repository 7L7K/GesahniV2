#!/usr/bin/env python3
"""
Test Google ID token with Google's tokeninfo endpoint.

This script verifies an ID token with Google's official tokeninfo endpoint
to confirm what Google actually returns for the issuer claim.

Usage:
    python test_google_tokeninfo.py YOUR_ID_TOKEN
    # OR
    ID_TOKEN="your_token" python test_google_tokeninfo.py
    # OR
    echo "your_token" | python test_google_tokeninfo.py
"""

import requests
import json
import os
import sys
from typing import Optional


def test_google_tokeninfo(token: str) -> dict:
    """Test ID token with Google's tokeninfo endpoint."""
    url = "https://oauth2.googleapis.com/tokeninfo"
    params = {"id_token": token}

    try:
        response = requests.get(url, params=params, timeout=10)
        return {
            "status_code": response.status_code,
            "response": response.json() if response.headers.get("content-type", "").startswith("application/json") else response.text,
            "headers": dict(response.headers),
            "success": response.status_code == 200
        }
    except Exception as e:
        return {
            "status_code": None,
            "response": f"Request failed: {e}",
            "headers": {},
            "success": False
        }


def main():
    # Get token from various sources
    token = None

    # Check command line arguments
    if len(sys.argv) > 1:
        token = sys.argv[1]
    # Check environment variable
    elif os.environ.get("ID_TOKEN"):
        token = os.environ.get("ID_TOKEN")
    # Check stdin
    elif not sys.stdin.isatty():
        token = sys.stdin.read().strip()

    if not token:
        print("Usage:")
        print("  python test_google_tokeninfo.py YOUR_ID_TOKEN")
        print("  ID_TOKEN='your_token' python test_google_tokeninfo.py")
        print("  echo 'your_token' | python test_google_tokeninfo.py")
        sys.exit(1)

    print("=== Google TokenInfo Verification ===")
    print(f"Token length: {len(token)} characters")
    print(f"Testing with Google tokeninfo endpoint...")
    print()

    # Test with Google's endpoint
    result = test_google_tokeninfo(token)

    print(f"HTTP Status: {result['status_code']}")
    print()

    if result["success"]:
        print("✓ Token verification successful")
        print("Response from Google:")
        print(json.dumps(result["response"], indent=2))
        print()

        # Analyze the response
        if isinstance(result["response"], dict):
            issuer = result["response"].get("iss")
            print("=== Issuer Analysis ===")
            print(f"Issuer (iss): {issuer}")

            if issuer:
                if issuer == "https://accounts.google.com":
                    print("✓ Issuer matches expected HTTPS format")
                elif issuer == "accounts.google.com":
                    print("⚠ Issuer missing HTTPS scheme (non-standard)")
                    print("  This might cause validation issues in some libraries")
                else:
                    print(f"✗ Unexpected issuer: {issuer}")
            else:
                print("✗ Missing issuer claim in Google's response!")

            # Check other important claims
            print()
            print("=== Other Claims ===")
            claims_to_check = ["sub", "aud", "exp", "iat", "email"]
            for claim in claims_to_check:
                value = result["response"].get(claim)
                print(f"{claim}: {value}")
        else:
            print("✗ Unexpected response format")
            print(f"Response: {result['response']}")
    else:
        print("✗ Token verification failed")
        print(f"Response: {result['response']}")
        print()

        if result["status_code"] == 400:
            print("Common causes:")
            print("- Invalid token format")
            print("- Token has expired")
            print("- Token was not issued by Google")
        elif result["status_code"] == 401:
            print("Token is invalid or malformed")


if __name__ == "__main__":
    main()
