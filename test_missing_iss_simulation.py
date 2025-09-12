#!/usr/bin/env python3
"""
Test simulation for missing_provider_iss error.

This script simulates the OAuth callback logic to test what happens
when Google returns an ID token without the 'iss' claim.
"""

import os
import sys

import jwt

# Add the app directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))


def create_mock_id_token(with_iss=True, issuer_value="https://accounts.google.com"):
    """Create a mock Google ID token."""
    payload = {
        "sub": "123456789012345678901",
        "aud": "test_client_id.apps.googleusercontent.com",
        "exp": 2000000000,
        "iat": 1000000000,
        "email": "test@example.com",
        "email_verified": True,
    }

    if with_iss:
        payload["iss"] = issuer_value

    # Create a JWT token (signature won't verify but that's ok for this test)
    token = jwt.encode(payload, "dummy_key", algorithm="HS256")
    return token, payload


def simulate_id_token_processing(id_token):
    """Simulate the ID token processing logic from the OAuth callback."""
    print(f"Simulating ID token processing for token: {id_token[:50]}...")

    try:
        # This is the logic from google_oauth.py callback
        from app.security import jwt_decode

        provider_sub = None
        provider_iss = None
        email = None

        try:
            claims = jwt_decode(id_token, options={"verify_signature": False})
            email = claims.get("email") or claims.get("email_address")
            provider_sub = claims.get("sub") or None
            provider_iss = claims.get("iss") or None

            print(f"✓ Decoded claims: sub={provider_sub}, iss={provider_iss}, email={email}")

            # Fallback for Google OAuth: if iss is missing, use standard Google issuer
            if not provider_iss and provider_sub:
                # This is likely a Google OAuth token if we have a sub but no iss
                provider_iss = "https://accounts.google.com"
                print(f"✓ Applied Google OAuth issuer fallback: {provider_iss}")

        except Exception as e:
            print(f"✗ Failed to decode ID token: {e}")

        # Check final result
        print(f"Final result: provider_iss={provider_iss}, provider_sub={provider_sub}")

        # This is the validation logic from the callback
        if not provider_iss:
            print("❌ Would trigger: missing_provider_iss error")
            return False
        else:
            print("✅ Validation would pass")
            return True

    except Exception as e:
        print(f"✗ Error in simulation: {e}")
        return False


def test_scenarios():
    """Test different scenarios."""
    print("=== Testing ID Token Processing Scenarios ===\n")

    # Scenario 1: Normal token with iss
    print("1. Normal Google ID token with 'iss' claim:")
    token1, payload1 = create_mock_id_token(with_iss=True)
    result1 = simulate_id_token_processing(token1)
    print()

    # Scenario 2: Token missing iss claim
    print("2. Google ID token MISSING 'iss' claim:")
    token2, payload2 = create_mock_id_token(with_iss=False)
    result2 = simulate_id_token_processing(token2)
    print()

    # Scenario 3: Token with different issuer format
    print("3. Google ID token with different issuer format:")
    token3, payload3 = create_mock_id_token(with_iss=True, issuer_value="accounts.google.com")
    result3 = simulate_id_token_processing(token3)
    print()

    # Summary
    print("=== Test Results Summary ===")
    print(f"✓ Normal token with iss: {'PASS' if result1 else 'FAIL'}")
    print(f"✓ Token missing iss: {'PASS' if result2 else 'FAIL'}")
    print(f"✓ Token with different issuer: {'PASS' if result3 else 'FAIL'}")

    if result2:
        print("\n🎉 The fallback logic works! Missing 'iss' claims are handled correctly.")
    else:
        print("\n❌ The fallback logic failed. This would cause the missing_provider_iss error.")

    return result1, result2, result3


def test_edge_cases():
    """Test edge cases that might cause issues."""
    print("\n=== Testing Edge Cases ===\n")

    # Test with malformed token
    print("1. Testing malformed token:")
    try:
        simulate_id_token_processing("invalid.jwt.token")
    except Exception as e:
        print(f"✗ Malformed token caused exception: {e}")
    print()

    # Test with empty token
    print("2. Testing empty token:")
    try:
        simulate_id_token_processing("")
    except Exception as e:
        print(f"✗ Empty token caused exception: {e}")
    print()

    # Test with token missing sub claim
    print("3. Testing token missing 'sub' claim:")
    payload_no_sub = {
        "aud": "test_client_id.apps.googleusercontent.com",
        "exp": 2000000000,
        "iat": 1000000000,
        "email": "test@example.com",
    }
    token_no_sub = jwt.encode(payload_no_sub, "dummy_key", algorithm="HS256")
    result_no_sub = simulate_id_token_processing(token_no_sub)
    print()


if __name__ == "__main__":
    test_scenarios()
    test_edge_cases()
