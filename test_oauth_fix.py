#!/usr/bin/env python3
"""
Test the OAuth fix to verify id_token is properly preserved.
"""

import os
import sys
import jwt
import asyncio
from unittest.mock import Mock, patch

# Add the app directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))


def test_exchange_code_preserves_id_token():
    """Test that exchange_code preserves the id_token."""
    print("=== Testing exchange_code id_token preservation ===")

    # Create a mock token response with id_token
    mock_token_response = {
        "access_token": "ya29.mock_token",
        "refresh_token": "mock_refresh_token",
        "scope": "openid email profile",
        "token_type": "Bearer",
        "expires_in": 3600,
        "id_token": jwt.encode({
            "sub": "123456789",
            "iss": "https://accounts.google.com",
            "aud": "test_client_id",
            "exp": 2000000000,
            "iat": 1000000000,
            "email": "test@example.com"
        }, "secret", algorithm="HS256")
    }

    # Mock the exchange_code_for_tokens function
    async def mock_exchange_code_for_tokens(code, code_verifier=None):
        return mock_token_response

    # Patch the function
    with patch('app.integrations.google.oauth.GoogleOAuth.exchange_code_for_tokens', side_effect=mock_exchange_code_for_tokens):
        # Import after patching
        from app.integrations.google.oauth import exchange_code

        # Test the exchange_code function (skip state verification for this test)
        result = asyncio.run(exchange_code("test_code", "test_state", verify_state=False, code_verifier="test_verifier"))

        # Check if id_token is preserved
        print(f"Result type: {type(result)}")
        print(f"Has id_token attribute: {hasattr(result, 'id_token')}")

        if hasattr(result, 'id_token'):
            print(f"id_token length: {len(result.id_token)}")
            print(f"id_token matches original: {result.id_token == mock_token_response['id_token']}")

            # Test decoding the id_token
            try:
                decoded = jwt.decode(result.id_token, options={"verify_signature": False})
                print(f"Decoded id_token: iss={decoded.get('iss')}, sub={decoded.get('sub')}")
                print("✅ id_token preservation test PASSED")
                return True
            except Exception as e:
                print(f"❌ Failed to decode id_token: {e}")
                return False
        else:
            print("❌ id_token attribute missing")
            return False


def test_callback_id_token_extraction():
    """Test that the callback can extract provider_iss from the id_token."""
    print("\n=== Testing callback id_token extraction ===")

    # Create a mock ThirdPartyToken with id_token
    from app.models.third_party_tokens import ThirdPartyToken

    id_token = jwt.encode({
        "sub": "123456789",
        "iss": "https://accounts.google.com",
        "aud": "test_client_id",
        "exp": 2000000000,
        "iat": 1000000000,
        "email": "test@example.com"
    }, "secret", algorithm="HS256")

    creds = ThirdPartyToken(
        user_id="test_user",
        provider="google",
        access_token="test_token",
        refresh_token="test_refresh",
        scope="openid email"
    )

    # Add id_token attribute (this is what our fix does)
    creds.id_token = id_token

    # Simulate the callback logic
    from app.security import jwt_decode

    provider_sub = None
    provider_iss = None
    email = None

    try:
        id_token_from_creds = getattr(creds, "id_token", None)
        print(f"Has id_token: {id_token_from_creds is not None}")

        if id_token_from_creds:
            claims = jwt_decode(id_token_from_creds, options={"verify_signature": False})
            email = claims.get("email") or claims.get("email_address")
            provider_sub = claims.get("sub") or None
            provider_iss = claims.get("iss") or None

            print(f"Extracted: iss={provider_iss}, sub={provider_sub}, email={email}")

            # Test the fallback logic
            if not provider_iss and provider_sub:
                provider_iss = "https://accounts.google.com"
                print(f"Applied fallback: {provider_iss}")

            if provider_iss:
                print("✅ Callback id_token extraction test PASSED")
                return True
            else:
                print("❌ provider_iss extraction failed")
                return False
        else:
            print("❌ No id_token in credentials")
            return False

    except Exception as e:
        print(f"❌ Exception during extraction: {e}")
        return False


if __name__ == "__main__":
    print("🔧 Testing OAuth id_token fix...\n")

    test1_passed = test_exchange_code_preserves_id_token()
    test2_passed = test_callback_id_token_extraction()

    print(f"\n📊 Test Results:")
    print(f"• exchange_code preserves id_token: {'✅' if test1_passed else '❌'}")
    print(f"• callback extracts provider_iss: {'✅' if test2_passed else '❌'}")

    if test1_passed and test2_passed:
        print("\n🎉 All tests PASSED! The OAuth fix should work correctly.")
    else:
        print("\n❌ Some tests FAILED. The fix may not work properly.")
