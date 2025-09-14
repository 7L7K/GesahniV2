#!/usr/bin/env python3
"""
Test Google OAuth scopes configuration.

This script verifies that the Google OAuth URL generation includes
the required 'openid' scope for ID token issuance.
"""

import os
import sys

# Add the app directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "app"))


def test_google_scopes():
    """Test that Google OAuth scopes include openid."""
    print("=== Google OAuth Scopes Verification ===")

    try:
        from app.integrations.google.config import get_google_scopes

        scopes = get_google_scopes()

        print(f"Configured scopes: {scopes}")
        print()

        # Check for openid scope
        has_openid = "openid" in scopes
        print(f"✓ Contains 'openid' scope: {has_openid}")

        if has_openid:
            print("  → This is required for Google to issue ID tokens")
        else:
            print(
                "  ✗ WARNING: Missing 'openid' scope - Google will not issue ID tokens!"
            )
            print("  → Add 'openid' to your GOOGLE_SCOPES environment variable")

        # Check for profile scopes
        has_email = "https://www.googleapis.com/auth/userinfo.email" in scopes
        has_profile = "https://www.googleapis.com/auth/userinfo.profile" in scopes

        print(f"✓ Contains email scope: {has_email}")
        print(f"✓ Contains profile scope: {has_profile}")

        print()
        print("=== OAuth URL Preview ===")

        # Test URL generation
        try:
            from app.integrations.google.oauth import GoogleOAuth

            oauth = GoogleOAuth()
            auth_url = oauth.get_authorization_url("test_state")

            print(f"Generated OAuth URL: {auth_url[:100]}...")
            print()

            # Check if URL contains openid
            if "openid" in auth_url:
                print("✓ OAuth URL contains 'openid' scope")
            else:
                print("✗ OAuth URL missing 'openid' scope!")

        except Exception as e:
            print(f"Error generating OAuth URL: {e}")
            print(
                "This might be due to missing GOOGLE_CLIENT_ID/SECRET environment variables"
            )

        return has_openid

    except ImportError as e:
        print(f"Error importing modules: {e}")
        return False


def test_oauth_flow_simulation():
    """Simulate the OAuth flow to identify potential issues."""
    print("\n=== OAuth Flow Simulation ===")

    try:
        # Test the JWT decode function
        import jwt

        from app.security import jwt_decode

        # Create a mock Google ID token payload
        mock_payload = {
            "iss": "https://accounts.google.com",
            "sub": "123456789",
            "aud": "test_client_id",
            "exp": 2000000000,
            "iat": 1000000000,
            "email": "test@example.com",
            "email_verified": True,
        }

        # Test jwt_decode function
        print("Testing JWT decode function...")
        decoded = jwt_decode(
            jwt.encode(mock_payload, "dummy_key", algorithm="HS256"),
            options={"verify_signature": False},
        )
        print(f"✓ JWT decode successful: iss={decoded.get('iss')}")

        # Test issuer validation logic
        provider_iss = decoded.get("iss")
        if provider_iss:
            print(f"✓ Provider issuer extracted: {provider_iss}")
            if provider_iss in ["https://accounts.google.com", "accounts.google.com"]:
                print("✓ Issuer validation would pass")
            else:
                print(f"✗ Issuer validation would fail: {provider_iss}")
        else:
            print("✗ No issuer found in decoded token")

    except Exception as e:
        print(f"Error in OAuth flow simulation: {e}")


if __name__ == "__main__":
    success = test_google_scopes()
    test_oauth_flow_simulation()

    if success:
        print("\n🎉 Google OAuth scopes configuration looks good!")
    else:
        print("\n❌ Google OAuth scopes configuration has issues!")
        sys.exit(1)
