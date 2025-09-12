#!/usr/bin/env python3
"""
Quick OAuth Fix Verification Script

Run this after completing an OAuth flow to verify the fix worked.
"""

import os
from datetime import datetime

import requests


def check_recent_logs():
    """Check recent logs for OAuth activity."""
    print("🔍 Checking recent OAuth logs...")

    try:
        # Try to read recent logs
        log_files = [
            "/Users/kingal/2025/GesahniV2/logs/backend.log",
            "/Users/kingal/2025/GesahniV2/logs/backend.log.backup"
        ]

        oauth_logs = []
        for log_file in log_files:
            if os.path.exists(log_file):
                try:
                    with open(log_file) as f:
                        lines = f.readlines()[-50:]  # Last 50 lines
                        for line in lines:
                            if any(keyword in line.lower() for keyword in ['google', 'oauth', 'id_token', 'provider_iss']):
                                oauth_logs.append(line.strip())
                except Exception:
                    pass

        if oauth_logs:
            print(f"📋 Found {len(oauth_logs)} OAuth-related log entries:")
            for i, log in enumerate(oauth_logs[-5:], 1):  # Show last 5
                print(f"  {i}. {log[:100]}{'...' if len(log) > 100 else ''}")
        else:
            print("❌ No recent OAuth logs found")
            print("   Complete an OAuth flow first, then run this script again")

        return len(oauth_logs) > 0

    except Exception as e:
        print(f"❌ Error checking logs: {e}")
        return False


def verify_server_running():
    """Verify the server is running."""
    print("🌐 Checking server status...")

    try:
        response = requests.get("http://127.0.0.1:8000/health", timeout=5)
        if response.status_code == 200:
            print("✅ Server is running and healthy")
            return True
        else:
            print(f"❌ Server responded with status {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Server not responding: {e}")
        print("   Start with: uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload")
        return False


def test_oauth_url_generation():
    """Test that OAuth URLs are generated correctly."""
    print("🔗 Testing OAuth URL generation...")

    try:
        response = requests.get("http://127.0.0.1:8000/v1/auth/google/login_url", timeout=5)
        if response.status_code == 200:
            data = response.json()
            auth_url = data.get('auth_url', '')

            if 'openid' in auth_url and 'state=' in auth_url:
                print("✅ OAuth URL generated correctly with openid scope")
                return True
            else:
                print("❌ OAuth URL missing required parameters")
                return False
        else:
            print(f"❌ OAuth URL endpoint failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Error testing OAuth URL: {e}")
        return False


def main():
    """Main verification function."""
    print("🔧 Google OAuth Fix Verification")
    print("=" * 40)
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # Run checks
    server_ok = verify_server_running()
    oauth_url_ok = test_oauth_url_generation() if server_ok else False
    logs_found = check_recent_logs()

    print("\n" + "=" * 40)
    print("📊 VERIFICATION RESULTS")

    if server_ok and oauth_url_ok:
        print("✅ CORE SYSTEMS: Working correctly")
        print("   • Backend server running")
        print("   • OAuth URL generation working")
        print("   • OpenID scope properly configured")
    else:
        print("❌ CORE SYSTEMS: Issues detected")
        if not server_ok:
            print("   • Backend server not running")
        if not oauth_url_ok:
            print("   • OAuth URL generation failed")

    if logs_found:
        print("✅ LOGGING: Recent OAuth activity detected")
        print("   • Enhanced logging is working")
        print("   • Check logs for detailed OAuth flow information")
    else:
        print("⚠️  LOGGING: No recent OAuth logs")
        print("   • Complete an OAuth flow to generate logs")

    print("\n" + "=" * 40)

    if server_ok and oauth_url_ok:
        print("🎯 STATUS: READY FOR TESTING")
        print("\nTo test the OAuth fix:")
        print("1. Open your frontend application")
        print("2. Navigate to Google OAuth integration")
        print("3. Click 'Connect with Google' or similar")
        print("4. Complete the Google OAuth flow")
        print("5. Check that you DON'T see 'missing_provider_iss' error")
        print("6. Run this script again to see the detailed logs")
        print("\nThe missing_provider_iss error should be resolved! 🚀")
    else:
        print("❌ STATUS: ISSUES DETECTED")
        print("\nFix the issues above before testing OAuth.")


if __name__ == "__main__":
    main()
