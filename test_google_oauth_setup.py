#!/usr/bin/env python3
"""
Test script to verify Google OAuth setup and configuration.
Run this after updating your .env file with real Google OAuth credentials.
"""

import os
from urllib.parse import parse_qs, urlparse

import requests


def test_google_oauth_config():
    """Test Google OAuth configuration and login URL generation."""

    print("🔍 Testing Google OAuth Configuration")
    print("=" * 50)

    # Check environment variables
    client_id = os.getenv("GOOGLE_CLIENT_ID", "")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "")
    redirect_uri = os.getenv("GOOGLE_REDIRECT_URI", "")

    print(
        f"📋 GOOGLE_CLIENT_ID: {'✅ Set' if client_id and client_id != 'YOUR_ACTUAL_GOOGLE_CLIENT_ID_HERE' else '❌ Not configured'}"
    )
    print(
        f"🔐 GOOGLE_CLIENT_SECRET: {'✅ Set' if client_secret and client_secret != 'YOUR_ACTUAL_GOOGLE_CLIENT_SECRET_HERE' else '❌ Not configured'}"
    )
    print(f"🔗 GOOGLE_REDIRECT_URI: {redirect_uri or '❌ Not set'}")

    if not client_id or client_id == "YOUR_ACTUAL_GOOGLE_CLIENT_ID_HERE":
        print("\n⚠️  WARNING: Google OAuth is not properly configured!")
        print("   Please update your .env file with real Google OAuth credentials.")
        print(
            "   See: https://console.cloud.google.com/ -> APIs & Services -> Credentials"
        )
        return False

    # Test login URL endpoint
    try:
        response = requests.get(
            "http://localhost:8000/v1/google/auth/login_url", timeout=5
        )
        if response.status_code == 200:
            data = response.json()
            auth_url = data.get("auth_url", "")

            print("\n🌐 Login URL Endpoint: ✅ Working")
            print(f"📨 Auth URL: {auth_url[:100]}...")

            # Parse the auth URL to verify it contains correct parameters
            parsed = urlparse(auth_url)
            params = parse_qs(parsed.query)

            expected_params = [
                "client_id",
                "redirect_uri",
                "response_type",
                "scope",
                "state",
            ]
            for param in expected_params:
                if param in params:
                    print(f"✅ {param}: {'✅' if params[param][0] else '❌'}")
                else:
                    print(f"❌ {param}: Missing")

            # Check if client_id in URL matches environment variable
            url_client_id = params.get("client_id", [""])[0]
            if url_client_id == client_id:
                print("✅ Client ID matches environment variable")
            else:
                print("❌ Client ID mismatch between URL and environment")

        else:
            print(f"❌ Login URL Endpoint failed: HTTP {response.status_code}")
            return False

    except requests.exceptions.RequestException as e:
        print(f"❌ Could not connect to backend: {e}")
        print("   Make sure the backend server is running on http://localhost:8000")
        return False

    print("\n🎉 Google OAuth appears to be configured correctly!")
    print("   Next steps:")
    print("   1. Test the OAuth flow by visiting the login URL in your browser")
    print("   2. Complete the Google OAuth consent flow")
    print("   3. Verify you get redirected back to the application")

    return True


if __name__ == "__main__":
    success = test_google_oauth_config()
    exit(0 if success else 1)
