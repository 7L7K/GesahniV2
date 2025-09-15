#!/usr/bin/env python3
"""
Test simulation for Google OAuth credentials object.

This script simulates different scenarios for the Google OAuth credentials
object to understand when the missing_provider_iss error might occur.
"""

import os
import sys
from unittest.mock import Mock

import jwt

# Add the app directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "app"))


def create_mock_credentials(has_id_token=True, id_token_content=None):
    """Create a mock Google OAuth credentials object."""
    creds = Mock()

    if has_id_token:
        if id_token_content is None:
            # Create a default ID token
            payload = {
                "sub": "123456789012345678901",
                "aud": "test_client_id.apps.googleusercontent.com",
                "exp": 2000000000,
                "iat": 1000000000,
                "email": "test@example.com",
                "email_verified": True,
            }
            creds.id_token = jwt.encode(payload, "dummy_key", algorithm="HS256")
        else:
            creds.id_token = id_token_content
    else:
        # No id_token attribute
        creds.id_token = None

    return creds


def simulate_oauth_callback_processing(creds):
    """Simulate the OAuth callback ID token processing."""
    id_token = getattr(creds, "id_token", None)
    if id_token:
        id_token_str = str(id_token)
        preview = id_token_str[:50] if len(id_token_str) > 50 else id_token_str
        print(f"Simulating OAuth callback with creds.id_token: {preview}")
    else:
        print("Simulating OAuth callback with creds.id_token: None")

    # This is the exact logic from google_oauth.py
    provider_sub = None
    provider_iss = None
    email = None

    try:
        id_token = getattr(creds, "id_token", None)
        print(f"id_token attribute: {'present' if id_token else 'missing'}")

        if id_token:
            from app.security import jwt_decode

            claims = jwt_decode(id_token, options={"verify_signature": False})
            email = claims.get("email") or claims.get("email_address")
            provider_sub = claims.get("sub") or None
            provider_iss = claims.get("iss") or None

            print(
                f"Decoded claims: sub={provider_sub}, iss={provider_iss}, email={email}"
            )

            # Fallback for Google OAuth: if iss is missing, use standard Google issuer
            if not provider_iss and provider_sub:
                provider_iss = "https://accounts.google.com"
                print(f"✓ Applied issuer fallback: {provider_iss}")
        else:
            print("✗ No id_token in credentials object")

    except Exception as e:
        print(f"✗ Exception during ID token processing: {e}")
        # In the real code, this would be logged as a warning

    print(f"Final result: provider_iss={provider_iss}, provider_sub={provider_sub}")

    # Simulate the database lookup fallback (simplified)
    if not provider_iss:
        print("Attempting database lookup fallback...")
        # Simulate database lookup - assume no existing token found
        existing_provider_iss = None  # This would come from database lookup

        if existing_provider_iss:
            provider_iss = existing_provider_iss
            print(f"✓ Recovered provider_iss from database: {provider_iss}")
        else:
            print("✗ No existing token found in database")

    # Final validation
    if not provider_iss:
        print("❌ Would trigger: missing_provider_iss error")
        return False, "missing_provider_iss"
    else:
        print("✅ Validation would pass")
        return True, None


def test_scenarios():
    """Test different credentials scenarios."""
    print("=== Testing Google OAuth Credentials Scenarios ===\n")

    scenarios = [
        (
            "Normal credentials with ID token",
            create_mock_credentials(has_id_token=True),
        ),
        (
            "Credentials with ID token missing iss",
            create_mock_credentials(
                has_id_token=True,
                id_token_content=jwt.encode(
                    {
                        "sub": "123456789012345678901",
                        "aud": "test_client_id.apps.googleusercontent.com",
                        "exp": 2000000000,
                        "iat": 1000000000,
                        "email": "test@example.com",
                    },
                    "dummy_key",
                    algorithm="HS256",
                ),
            ),
        ),
        ("Credentials without ID token", create_mock_credentials(has_id_token=False)),
        (
            "Credentials with malformed ID token",
            create_mock_credentials(
                has_id_token=True, id_token_content="malformed.jwt.token"
            ),
        ),
    ]

    results = []

    for i, (description, creds) in enumerate(scenarios, 1):
        print(f"{i}. {description}:")
        success, error = simulate_oauth_callback_processing(creds)
        results.append((description, success, error))
        print()

    print("=== Test Results Summary ===")
    for description, success, error in results:
        status = "✅ PASS" if success else f"❌ FAIL ({error})"
        print(f"{status}: {description}")

    # Check which scenarios would cause the missing_provider_iss error
    failing_scenarios = [desc for desc, success, _ in results if not success]

    if failing_scenarios:
        print("\n⚠️  The following scenarios would trigger missing_provider_iss:")
        for scenario in failing_scenarios:
            print(f"   • {scenario}")
    else:
        print(
            "\n🎉 All scenarios passed! The missing_provider_iss error should not occur."
        )

    return results


def test_real_world_scenario():
    """Test a scenario that might occur in the real world."""
    print("\n=== Testing Real-World Scenario ===")
    print("Simulating what happens when Google returns credentials but no id_token")
    print("(This can happen if the OAuth scope configuration is incorrect)")
    print()

    # This simulates a common real-world issue where Google doesn't return
    # an id_token even though the openid scope was requested
    creds_no_id_token = Mock()
    # No id_token attribute at all

    success, error = simulate_oauth_callback_processing(creds_no_id_token)

    if not success and error == "missing_provider_iss":
        print("\n💡 Root Cause Identified:")
        print("   Google OAuth is not returning an id_token in the token response.")
        print("   This can happen if:")
        print("   • The 'openid' scope was not properly requested")
        print("   • Google's token endpoint has an issue")
        print("   • The client configuration is missing id_token support")
        print("\n🔧 Suggested Fix:")
        print("   1. Verify 'openid' scope is in GOOGLE_SCOPES")
        print("   2. Check Google Cloud Console OAuth client configuration")
        print("   3. Ensure the authorization request includes openid scope")
    else:
        print("This scenario would not cause the missing_provider_iss error.")


if __name__ == "__main__":
    test_scenarios()
    test_real_world_scenario()
