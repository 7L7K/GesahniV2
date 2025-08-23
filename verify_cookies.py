#!/usr/bin/env python3
"""
Simple script to verify the exact cookie headers being set.
This shows the raw Set-Cookie headers for manual verification.
"""

import requests

# Configuration
API_URL = "http://localhost:8000"
TEST_USERNAME = "testuser"
TEST_PASSWORD = "testpass123"


def main():
    print("🔍 Verifying Cookie Headers")
    print("=" * 50)

    # Test login
    print("1. Login Response Headers:")
    print("-" * 30)

    try:
        login_data = {"username": TEST_USERNAME, "password": TEST_PASSWORD}

        response = requests.post(f"{API_URL}/v1/login", json=login_data)

        print(f"Status: {response.status_code}")
        print(f"Content-Type: {response.headers.get('content-type', 'N/A')}")
        print()

        # Show all Set-Cookie headers
        set_cookie_headers = response.headers.get("set-cookie", "")
        if set_cookie_headers:
            print("Set-Cookie Headers:")
            if isinstance(set_cookie_headers, str):
                # Split multiple cookies
                cookies = set_cookie_headers.split(", ")
                for i, cookie in enumerate(cookies, 1):
                    print(f"  {i}. {cookie}")
            else:
                for i, cookie in enumerate(set_cookie_headers, 1):
                    print(f"  {i}. {cookie}")
        else:
            print("No Set-Cookie headers found")

        print()

        # Test logout
        print("2. Logout Response Headers:")
        print("-" * 30)

        # Extract cookies for logout
        session_cookies = {}
        if set_cookie_headers:
            if isinstance(set_cookie_headers, str):
                cookies = set_cookie_headers.split(", ")
                for cookie in cookies:
                    if "=" in cookie:
                        name = cookie.split("=")[0]
                        value = cookie.split("=")[1].split(";")[0]
                        session_cookies[name] = value

        logout_response = requests.post(
            f"{API_URL}/v1/auth/logout", cookies=session_cookies
        )

        print(f"Status: {logout_response.status_code}")
        print()

        # Show logout Set-Cookie headers
        logout_set_cookie_headers = logout_response.headers.get("set-cookie", "")
        if logout_set_cookie_headers:
            print("Logout Set-Cookie Headers (clearing):")
            if isinstance(logout_set_cookie_headers, str):
                cookies = logout_set_cookie_headers.split(", ")
                for i, cookie in enumerate(cookies, 1):
                    print(f"  {i}. {cookie}")
            else:
                for i, cookie in enumerate(logout_set_cookie_headers, 1):
                    print(f"  {i}. {cookie}")
        else:
            print("No logout Set-Cookie headers found")

        print()
        print("=" * 50)
        print("✅ Cookie Configuration Verification Complete")
        print()
        print("Expected attributes per cookie:")
        print("  ✓ Path=/")
        print("  ✓ HttpOnly")
        print("  ✓ SameSite=Lax")
        print("  ✓ No Secure (for dev HTTP)")
        print("  ✓ No Domain (host-only)")
        print("  ✓ Max-Age: access ~15m (900s), refresh ~30d (2592000s)")
        print("  ✓ Priority=High")
        print("  ✓ Delete flow: identical attrs + Max-Age=0")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
