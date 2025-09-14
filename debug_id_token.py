#!/usr/bin/env python3
"""
Debug script to decode Google ID tokens locally and verify issuer claim.

This script helps debug the "missing_provider_iss" error by:
1. Decoding the ID token without signature verification
2. Checking if the "iss" claim is present
3. Validating the issuer against Google's expected values

Usage:
    echo "YOUR_ID_TOKEN_HERE" | python debug_id_token.py
    # OR
    python debug_id_token.py YOUR_ID_TOKEN_HERE
    # OR set ID_TOKEN environment variable
    ID_TOKEN="your_token" python debug_id_token.py
"""

import base64
import json
import os
import sys

import jwt


def decode_id_token_locally(token: str) -> tuple[dict, dict]:
    """Decode ID token without signature verification and return header/payload."""
    try:
        # Decode header
        header_b64 = token.split(".")[0]
        # Add padding if needed
        header_b64 += "=" * ((4 - len(header_b64) % 4) % 4)
        header_bytes = base64.urlsafe_b64decode(header_b64)
        header = json.loads(header_bytes.decode())

        # Decode payload without verification
        payload = jwt.decode(token, options={"verify_signature": False})

        return header, payload
    except Exception as e:
        print(f"Error decoding token: {e}")
        return {}, {}


def validate_google_issuer(issuer: str | None) -> tuple[bool, str]:
    """Validate that the issuer is a valid Google issuer."""
    if not issuer:
        return False, "Missing issuer claim"

    # Google uses these issuer values
    valid_issuers = [
        "https://accounts.google.com",
        "accounts.google.com",  # Sometimes without scheme
    ]

    if issuer in valid_issuers:
        return True, f"Valid Google issuer: {issuer}"
    else:
        return False, f"Invalid issuer: {issuer} (expected one of {valid_issuers})"


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
        print("  echo 'YOUR_ID_TOKEN' | python debug_id_token.py")
        print("  python debug_id_token.py YOUR_ID_TOKEN")
        print("  ID_TOKEN='your_token' python debug_id_token.py")
        sys.exit(1)

    print("=== Google ID Token Decoder ===")
    print(f"Token length: {len(token)} characters")
    print()

    # Decode the token
    header, payload = decode_id_token_locally(token)

    print("HEADER:")
    print(json.dumps(header, indent=2))
    print()

    print("PAYLOAD:")
    print(json.dumps(payload, indent=2))
    print()

    # Validate issuer
    issuer = payload.get("iss")
    is_valid, message = validate_google_issuer(issuer)

    print("=== Issuer Validation ===")
    print(f"Issuer claim: {issuer}")
    print(f"Validation: {'✓ PASS' if is_valid else '✗ FAIL'}")
    print(f"Message: {message}")
    print()

    # Additional checks
    print("=== Additional Claims Check ===")
    required_claims = ["iss", "sub", "aud", "exp", "iat"]
    missing_claims = []

    for claim in required_claims:
        if claim not in payload:
            missing_claims.append(claim)

    if missing_claims:
        print(f"✗ Missing required claims: {missing_claims}")
    else:
        print("✓ All required claims present")

    # Check if this looks like a Google token
    has_google_indicators = (
        issuer
        and ("google" in issuer.lower() or "accounts.google.com" in issuer)
        or payload.get("email")
        or payload.get("email_verified") is not None
    )

    print(
        f"Google token indicators: {'✓ Present' if has_google_indicators else '✗ Missing'}"
    )

    if not is_valid:
        print()
        print("=== Troubleshooting ===")
        print("1. Ensure your OAuth request includes the 'openid' scope")
        print("2. Check that you're requesting an ID token (not just access token)")
        print("3. Verify your client configuration in Google Cloud Console")
        print("4. Test with Google's tokeninfo endpoint:")
        print(
            f"   curl -s 'https://oauth2.googleapis.com/tokeninfo?id_token={token[:50]}...' | jq ."
        )


if __name__ == "__main__":
    main()
