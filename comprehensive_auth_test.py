#!/usr/bin/env python3
"""
Comprehensive Authentication Testing Suite

Tests all aspects of authentication flow to identify frontend/backend issues.
"""

import json
import os
import subprocess
import time
from datetime import UTC, datetime


def run_curl_test(
    description, cmd_parts, expected_status=200, expect_cookies=False, expect_auth=False
):
    """Run a curl test with comprehensive output."""
    print(f"\n{'🔍' * 3} {description} {'🔍' * 3}")
    print(f"Command: {' '.join(cmd_parts)}")

    try:
        result = subprocess.run(cmd_parts, capture_output=True, text=True, timeout=30)

        print(f"Status: {result.returncode} {'✅' if result.returncode == 0 else '❌'}")

        # Show headers
        if result.stderr:
            print("\n📋 HEADERS:")
            in_headers = False
            for line in result.stderr.split("\n"):
                if line.startswith("< ") or line.startswith("> "):
                    in_headers = True
                    print(f"  {line}")
                elif in_headers and line.strip():
                    print(f"  {line}")

        # Show response
        if result.stdout:
            print("\n📄 RESPONSE:")
            try:
                data = json.loads(result.stdout)
                print(f"  {json.dumps(data, indent=2)}")
            except:
                print(
                    f"  {result.stdout[:500]}{'...' if len(result.stdout) > 500 else ''}"
                )

        # Check for expected outcomes
        if expect_cookies and "set-cookie:" in result.stderr.lower():
            print("✅ Cookies set correctly")
        elif expect_cookies:
            print("⚠️  No cookies found in response")

        if expect_auth and result.stdout:
            try:
                data = json.loads(result.stdout)
                if data.get("is_authenticated"):
                    print("✅ Authentication successful")
                else:
                    print("❌ Authentication failed")
            except:
                pass

        return result
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return None


def main():
    """Run comprehensive authentication tests."""
    print("🚀 COMPREHENSIVE AUTHENTICATION TESTING SUITE")
    print(f"⏰ {datetime.now(UTC).isoformat()}")

    base_url = "http://localhost:8000"

    # Clean up any existing cookies
    if os.path.exists("/tmp/test_cookies.txt"):
        os.remove("/tmp/test_cookies.txt")

    # ============================================================================
    # TEST 1: Basic Health Check
    # ============================================================================
    run_curl_test("HEALTH CHECK", ["curl", "-s", f"{base_url}/healthz/ready"])

    # ============================================================================
    # TEST 2: Initial Whoami (should be unauthenticated)
    # ============================================================================
    run_curl_test("INITIAL WHOAMI", ["curl", "-v", f"{base_url}/v1/whoami"])

    # ============================================================================
    # TEST 3: Login with different methods
    # ============================================================================

    # 3a: Standard login
    run_curl_test(
        "LOGIN - Standard",
        [
            "curl",
            "-v",
            "-X",
            "POST",
            "-H",
            "Content-Type: application/json",
            "-d",
            "{}",
            f"{base_url}/v1/auth/login?username=qazwsxppo",
        ],
        expect_cookies=True,
    )

    # 3b: Login with cookie saving
    run_curl_test(
        "LOGIN - Save Cookies",
        [
            "curl",
            "-v",
            "-X",
            "POST",
            "-H",
            "Content-Type: application/json",
            "-d",
            "{}",
            "-c",
            "/tmp/test_cookies.txt",
            f"{base_url}/v1/auth/login?username=qazwsxppo",
        ],
        expect_cookies=True,
    )

    # ============================================================================
    # TEST 4: Whoami with cookies
    # ============================================================================
    if os.path.exists("/tmp/test_cookies.txt"):
        run_curl_test(
            "WHOAMI - With Cookies",
            ["curl", "-v", "-b", "/tmp/test_cookies.txt", f"{base_url}/v1/whoami"],
            expect_auth=True,
        )

    # ============================================================================
    # TEST 5: Test different user agents
    # ============================================================================
    run_curl_test(
        "LOGIN - Browser User Agent",
        [
            "curl",
            "-v",
            "-X",
            "POST",
            "-H",
            "Content-Type: application/json",
            "-H",
            "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "-d",
            "{}",
            "-c",
            "/tmp/browser_cookies.txt",
            f"{base_url}/v1/auth/login?username=qazwsxppo",
        ],
        expect_cookies=True,
    )

    if os.path.exists("/tmp/browser_cookies.txt"):
        run_curl_test(
            "WHOAMI - Browser Cookies",
            [
                "curl",
                "-v",
                "-H",
                "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
                "-b",
                "/tmp/browser_cookies.txt",
                f"{base_url}/v1/whoami",
            ],
            expect_auth=True,
        )

    # ============================================================================
    # TEST 6: Test CORS headers
    # ============================================================================
    run_curl_test(
        "LOGIN - CORS Headers",
        [
            "curl",
            "-v",
            "-X",
            "POST",
            "-H",
            "Content-Type: application/json",
            "-H",
            "Origin: http://localhost:3000",
            "-H",
            "Referer: http://localhost:3000/login",
            "-d",
            "{}",
            "-c",
            "/tmp/cors_cookies.txt",
            f"{base_url}/v1/auth/login?username=qazwsxppo",
        ],
        expect_cookies=True,
    )

    # ============================================================================
    # TEST 7: Test different endpoints
    # ============================================================================
    endpoints = ["/v1/sessions", "/v1/pats", "/v1/csrf", "/v1/integrations/status"]

    for endpoint in endpoints:
        if os.path.exists("/tmp/test_cookies.txt"):
            run_curl_test(
                f"TEST {endpoint.upper()}",
                ["curl", "-v", "-b", "/tmp/test_cookies.txt", f"{base_url}{endpoint}"],
                expected_status=200,
            )
        else:
            print(f"\n⚠️  Skipping {endpoint} - no cookies available")

    # ============================================================================
    # TEST 8: Test cookie persistence
    # ============================================================================
    if os.path.exists("/tmp/test_cookies.txt"):
        print("\n⏰ WAITING 5 SECONDS TO TEST COOKIE PERSISTENCE...")
        time.sleep(5)

        run_curl_test(
            "WHOAMI - Cookie Persistence Test",
            ["curl", "-v", "-b", "/tmp/test_cookies.txt", f"{base_url}/v1/whoami"],
            expect_auth=True,
        )

    # ============================================================================
    # TEST 9: Test with different cookie formats
    # ============================================================================
    if os.path.exists("/tmp/test_cookies.txt"):
        # Create a manual cookie header
        with open("/tmp/test_cookies.txt") as f:
            content = f.read()

        cookies = []
        for line in content.split("\n"):
            if line and not line.startswith("#") and "\t" in line:
                parts = line.split("\t")
                if len(parts) >= 6 and parts[5] in ["GSNH_AT", "GSNH_RT", "GSNH_SESS"]:
                    name = parts[5]
                    value = parts[6] if len(parts) > 6 else ""
                    cookies.append(f"{name}={value}")

        if cookies:
            cookie_header = "; ".join(cookies)
            run_curl_test(
                "WHOAMI - Manual Cookie Header",
                [
                    "curl",
                    "-v",
                    "-H",
                    f"Cookie: {cookie_header}",
                    f"{base_url}/v1/whoami",
                ],
                expect_auth=True,
            )

    # ============================================================================
    # TEST 10: Test logout
    # ============================================================================
    if os.path.exists("/tmp/test_cookies.txt"):
        run_curl_test(
            "LOGOUT",
            [
                "curl",
                "-v",
                "-b",
                "/tmp/test_cookies.txt",
                "-X",
                "POST",
                f"{base_url}/v1/auth/logout",
            ],
        )

        # Test whoami after logout
        run_curl_test(
            "WHOAMI - After Logout",
            ["curl", "-v", "-b", "/tmp/test_cookies.txt", f"{base_url}/v1/whoami"],
        )

    # ============================================================================
    # SUMMARY
    # ============================================================================
    print("\n🎯 TEST SUMMARY")
    print("📊 Check the output above for:")
    print("  ✅ Successful authentications")
    print("  🍪 Cookie setting/storage")
    print("  🔄 Token refresh behavior")
    print("  🚪 Logout functionality")
    print("  🌐 CORS and cross-origin issues")

    # Show cookie files
    for cookie_file in [
        "/tmp/test_cookies.txt",
        "/tmp/browser_cookies.txt",
        "/tmp/cors_cookies.txt",
    ]:
        if os.path.exists(cookie_file):
            print(f"\n📋 COOKIES IN {cookie_file}:")
            with open(cookie_file) as f:
                content = f.read()
                for line in content.split("\n"):
                    if line and not line.startswith("#") and "\t" in line:
                        parts = line.split("\t")
                        if len(parts) >= 6:
                            name = parts[5]
                            print(f"  🍪 {name}")

    print(f"\n🎉 TESTING COMPLETE - {datetime.now(UTC).isoformat()}")


if __name__ == "__main__":
    main()
