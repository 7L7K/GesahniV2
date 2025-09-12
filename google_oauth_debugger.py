#!/usr/bin/env python3
"""
Google OAuth ID Token Issuer Debugger

Complete toolkit for diagnosing and fixing the "missing_provider_iss" error
in Google OAuth ID token validation.

This error occurs when Google's ID token doesn't include the required 'iss' (issuer) claim,
causing the OAuth callback to fail with a 400 error.

Usage:
    python google_oauth_debugger.py
"""

import json
import os
import subprocess
import sys
from pathlib import Path


def print_header():
    """Print the header information."""
    print("🔍 Google OAuth ID Token Issuer Debugger")
    print("=" * 60)
    print()
    print("This toolkit helps diagnose the 'missing_provider_iss' error that occurs")
    print("when Google OAuth ID tokens don't include the required 'iss' claim.")
    print()
    print("Available debugging tools:")
    print("1. Local ID token decoder")
    print("2. Google tokeninfo verification")
    print("3. OAuth scopes verification")
    print("4. Complete OAuth flow diagnostic")
    print()


def run_script(script_name, description):
    """Run a diagnostic script and display results."""
    script_path = Path(__file__).parent / script_name

    if not script_path.exists():
        print(f"❌ {script_name} not found")
        return

    print(f"\n🔧 Running {description}...")
    print("-" * 40)

    try:
        # Set PYTHONPATH for imports
        env = os.environ.copy()
        env['PYTHONPATH'] = str(Path(__file__).parent)

        result = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True,
            text=True,
            env=env,
            cwd=Path(__file__).parent
        )

        if result.returncode == 0:
            print(result.stdout)
        else:
            print(f"❌ Script failed with exit code {result.returncode}")
            print("STDOUT:", result.stdout)
            print("STDERR:", result.stderr)

    except Exception as e:
        print(f"❌ Error running {script_name}: {e}")


def show_usage_examples():
    """Show examples of how to use the debugging tools."""
    print("\n📚 Usage Examples")
    print("-" * 20)

    print("1. Decode an ID token locally:")
    print("   echo 'YOUR_ID_TOKEN' | python debug_id_token.py")
    print()

    print("2. Verify ID token with Google:")
    print("   echo 'YOUR_ID_TOKEN' | python test_google_tokeninfo.py")
    print()

    print("3. Test OAuth scopes configuration:")
    print("   PYTHONPATH=. python test_oauth_scopes.py")
    print()

    print("4. Run full OAuth flow diagnostic:")
    print("   PYTHONPATH=. python test_oauth_flow.py")
    print()

    print("5. Monitor OAuth logs in real-time:")
    print("   tail -f logs/backend.log | grep -E '(oauth|google|callback|iss)'")
    print()


def show_troubleshooting_guide():
    """Show the troubleshooting guide."""
    print("\n🔧 Troubleshooting Guide")
    print("-" * 25)

    print("ISSUE: missing_provider_iss error in Google OAuth callback")
    print()

    print("Step 1: Verify OAuth Configuration")
    print("✓ Check that GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET are set")
    print("✓ Verify GOOGLE_SCOPES includes 'openid'")
    print("✓ Confirm redirect URI matches Google Cloud Console")
    print()

    print("Step 2: Test OAuth URL Generation")
    print("✓ Run: PYTHONPATH=. python test_oauth_scopes.py")
    print("✓ Verify 'openid' scope appears in generated URL")
    print()

    print("Step 3: Perform OAuth Flow")
    print("✓ Start backend: uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload")
    print("✓ Start frontend: cd frontend && npm run dev")
    print("✓ Navigate to Google OAuth integration")
    print("✓ Complete OAuth flow with Google account")
    print()

    print("Step 4: Monitor and Capture")
    print("✓ Watch logs: tail -f logs/backend.log")
    print("✓ Look for ID tokens in callback logs")
    print("✓ Extract any ID tokens for testing")
    print()

    print("Step 5: Analyze ID Tokens")
    print("✓ Test locally: echo 'TOKEN' | python debug_id_token.py")
    print("✓ Verify with Google: echo 'TOKEN' | python test_google_tokeninfo.py")
    print("✓ Check for 'iss' claim presence")
    print()

    print("Common Issues and Fixes:")
    print("• Missing 'openid' scope → Add to GOOGLE_SCOPES")
    print("• Google Cloud Console misconfiguration → Verify client settings")
    print("• ID token decoding failure → Check JWT library compatibility")
    print("• Fallback logic not triggering → Verify provider_sub extraction")
    print()


def show_expected_behavior():
    """Show what the expected behavior should be."""
    print("\n✅ Expected Behavior")
    print("-" * 20)

    print("When Google OAuth works correctly:")
    print("1. OAuth URL includes 'openid' scope")
    print("2. Google issues ID token with 'iss' claim")
    print("3. ID token contains: iss, sub, aud, exp, iat")
    print("4. Callback successfully extracts provider_iss")
    print("5. Token validation passes")
    print()

    print("Valid Google issuer values:")
    print("• https://accounts.google.com (with HTTPS)")
    print("• accounts.google.com (without scheme)")
    print()

    print("ID token should look like:")
    sample_token = {
        "iss": "https://accounts.google.com",
        "sub": "123456789012345678901",
        "aud": "your-client-id.apps.googleusercontent.com",
        "exp": 1634567890,
        "iat": 1634567290,
        "email": "user@example.com",
        "email_verified": True
    }
    print(json.dumps(sample_token, indent=2))


def main():
    """Main function."""
    print_header()

    # Run all diagnostic scripts
    run_script("test_oauth_scopes.py", "OAuth Scopes Verification")
    run_script("test_oauth_flow.py", "OAuth Flow Diagnostic")

    # Show usage and troubleshooting
    show_usage_examples()
    show_troubleshooting_guide()
    show_expected_behavior()

    print("\n🎯 Next Steps")
    print("-" * 12)
    print("1. Run the OAuth flow manually to reproduce the error")
    print("2. Capture ID tokens from logs")
    print("3. Use the debug scripts to analyze any tokens found")
    print("4. Report findings for further investigation")
    print()
    print("📧 If you encounter issues, share:")
    print("   • OAuth callback logs")
    print("   • ID token content (if available)")
    print("   • Debug script outputs")
    print("   • Google Cloud Console client configuration")


if __name__ == "__main__":
    main()
