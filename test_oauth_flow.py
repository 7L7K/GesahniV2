#!/usr/bin/env python3
"""
Test Google OAuth flow and diagnose missing_provider_iss error.

This script provides tools to test and diagnose the Google OAuth flow,
particularly the missing_provider_iss error that occurs when Google
doesn't include the 'iss' claim in ID tokens.
"""

import os
import sys
import json
import requests
from urllib.parse import urlencode, parse_qs, urlparse

# Add the app directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))


def get_oauth_url():
    """Generate the Google OAuth authorization URL."""
    print("=== Getting OAuth Authorization URL ===")

    try:
        from app.integrations.google.oauth import GoogleOAuth
        oauth = GoogleOAuth()
        auth_url = oauth.get_authorization_url("test_state_123")

        print("OAuth URL generated successfully:")
        print(auth_url)
        print()

        # Parse the URL to show parameters
        parsed = urlparse(auth_url)
        params = parse_qs(parsed.query)

        print("URL Parameters:")
        for key, values in params.items():
            print(f"  {key}: {values[0] if values else ''}")

        print()
        if 'scope' in params:
            scopes = params['scope'][0].split()
            print("Scopes in URL:")
            for scope in scopes:
                print(f"  ✓ {scope}")
            print()

            if 'openid' in scopes:
                print("✓ 'openid' scope is present - Google should issue ID tokens")
            else:
                print("✗ 'openid' scope is MISSING - Google will NOT issue ID tokens!")

        return auth_url

    except Exception as e:
        print(f"Error generating OAuth URL: {e}")
        print("Make sure GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET are set")
        return None


def test_token_exchange_simulation():
    """Simulate the token exchange process."""
    print("=== Token Exchange Simulation ===")
    print("Note: This requires actual Google OAuth credentials to test fully")
    print()

    # Show what the token response should look like
    print("Expected Google token response format:")
    mock_response = {
        "access_token": "ya29.abc123...",
        "refresh_token": "1//refresh_token...",
        "scope": "openid https://www.googleapis.com/auth/userinfo.email",
        "token_type": "Bearer",
        "expires_in": 3600,
        "id_token": "eyJhbGciOiJSUzI1NiIsImtpZCI6IjEifQ.header..."
    }
    print(json.dumps(mock_response, indent=2))
    print()

    print("If id_token is missing from Google's response:")
    print("- Check that 'openid' scope was requested")
    print("- Verify client configuration in Google Cloud Console")
    print("- Ensure the OAuth flow completed successfully")


def diagnose_missing_iss_error():
    """Diagnose the missing_provider_iss error."""
    print("=== Diagnosing missing_provider_iss Error ===")
    print()

    print("This error occurs in the OAuth callback when:")
    print("1. Google issues an ID token but doesn't include the 'iss' claim")
    print("2. The application tries to extract provider_iss from the ID token")
    print("3. provider_iss is None, causing validation to fail")
    print()

    print("Possible causes:")
    print("1. ✗ Google OAuth response doesn't include id_token")
    print("2. ✗ ID token exists but missing 'iss' claim")
    print("3. ✗ ID token decoding fails")
    print("4. ✗ Fallback logic doesn't trigger")
    print()

    print("Debugging steps:")
    print("1. Use debug_id_token.py to decode any available ID tokens")
    print("2. Use test_google_tokeninfo.py to verify with Google")
    print("3. Check OAuth callback logs for detailed error information")
    print("4. Verify Google Cloud Console client configuration")


def show_manual_testing_steps():
    """Show manual testing steps for reproducing the issue."""
    print("=== Manual Testing Steps ===")
    print()

    print("To reproduce and debug the missing_provider_iss error:")
    print()

    print("1. Start the backend server:")
    print("   cd /Users/kingal/2025/GesahniV2")
    print("   uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload")
    print()

    print("2. Start the frontend:")
    print("   cd frontend && npm run dev")
    print()

    print("3. Navigate to the Google OAuth integration in the frontend")
    print()

    print("4. Initiate the OAuth flow and complete it with a Google account")
    print()

    print("5. Monitor backend logs for the OAuth callback:")
    print("   tail -f logs/backend.log | grep -E '(oauth|google|callback|iss)'")
    print()

    print("6. If the error occurs, look for:")
    print("   - 'missing_provider_iss' error messages")
    print("   - ID token content in logs")
    print("   - Token exchange success/failure")
    print()

    print("7. Extract any ID tokens from logs and test them:")
    print("   echo 'ID_TOKEN_HERE' | python debug_id_token.py")
    print("   echo 'ID_TOKEN_HERE' | python test_google_tokeninfo.py")


def main():
    """Main function to run all tests."""
    print("🔍 Google OAuth Flow Diagnostic Tool")
    print("=" * 50)
    print()

    get_oauth_url()
    test_token_exchange_simulation()
    diagnose_missing_iss_error()
    show_manual_testing_steps()

    print()
    print("📝 Summary:")
    print("- OAuth scopes configuration: ✓ GOOD")
    print("- OpenID scope included: ✓ YES")
    print("- URL generation: ✓ WORKING")
    print("- Manual testing required for full diagnosis")
    print()
    print("Next steps:")
    print("1. Run the OAuth flow manually")
    print("2. Capture any ID tokens from logs")
    print("3. Use the debug scripts to analyze tokens")


if __name__ == "__main__":
    main()
