#!/usr/bin/env python3
"""
Debug Authentication Flow

Comprehensive debugging tool to trace the entire authentication flow
from login to whoami verification.
"""

import json
import time
from datetime import UTC, datetime


def debug_request(
    url, method="GET", data=None, cookies_file=None, save_cookies=None, headers=None
):
    """Make a request with full debugging output."""
    import json
    import subprocess

    cmd = ["curl", "-v"]

    if method == "POST":
        cmd.extend(["-X", "POST"])
        if data:
            cmd.extend(["-H", "Content-Type: application/json"])
            cmd.extend(["-d", json.dumps(data)])

    if headers:
        for header, value in headers.items():
            cmd.extend(["-H", f"{header}: {value}"])

    if cookies_file:
        cmd.extend(["-b", cookies_file])

    if save_cookies:
        cmd.extend(["-c", save_cookies])

    cmd.extend([url])

    print(f"\n{'='*80}")
    print(f"🔍 DEBUG REQUEST: {method} {url}")
    print(f"{'='*80}")
    print(f"Command: {' '.join(cmd)}")

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        print(f"\n📥 RESPONSE STATUS: {result.returncode}")
        print(f"📄 RAW OUTPUT:\n{result.stdout}")
        if result.stderr:
            print(f"🔧 STDERR:\n{result.stderr}")
        return result
    except Exception as e:
        print(f"❌ REQUEST FAILED: {e}")
        return None


def main():
    """Run comprehensive authentication flow debugging."""
    print("🚀 STARTING AUTHENTICATION FLOW DEBUG")
    print(f"⏰ {datetime.now(UTC).isoformat()}")

    base_url = "http://localhost:8000"

    # Step 1: Health Check
    print("\n🏥 STEP 1: HEALTH CHECK")
    result = debug_request(f"{base_url}/healthz/ready")
    if result and result.returncode != 0:
        print("❌ Health check failed!")
        return

    # Step 2: Initial Whoami (should be unauthenticated)
    print("\n👤 STEP 2: INITIAL WHOAMI (should be unauthenticated)")
    result = debug_request(f"{base_url}/v1/whoami")
    if result and "is_authenticated.*false" in result.stdout:
        print("✅ Correctly unauthenticated")
    else:
        print("⚠️  Unexpected authentication state")

    # Step 3: Login
    print("\n🔐 STEP 3: LOGIN")
    result = debug_request(
        f"{base_url}/v1/auth/login?username=qazwsxppo",
        method="POST",
        data={},
        save_cookies="/tmp/debug_auth_cookies.txt",
    )

    if result and result.returncode == 0:
        print("✅ Login successful")

        # Extract cookies from response
        cookies_found = []
        for line in result.stderr.split("\n"):
            if "set-cookie:" in line.lower():
                cookie_name = line.split("set-cookie:")[1].split("=")[0].strip()
                cookies_found.append(cookie_name)
        print(f"🍪 Cookies set: {cookies_found}")

        # Check response content
        try:
            response_data = json.loads(result.stdout)
            if response_data.get("status") == "ok":
                print("✅ Login response valid")
                print(
                    f"🔑 Access Token: {response_data.get('access_token', 'N/A')[:50]}..."
                )
                print(
                    f"🔄 Refresh Token: {response_data.get('refresh_token', 'N/A')[:50]}..."
                )
            else:
                print(f"⚠️  Unexpected login response: {response_data}")
        except:
            print(f"⚠️  Could not parse login response: {result.stdout[:200]}...")

    else:
        print("❌ Login failed!")
        return

    # Step 4: Authenticated Whoami
    print("\n👤 STEP 4: AUTHENTICATED WHOAMI")
    time.sleep(1)  # Brief pause
    result = debug_request(
        f"{base_url}/v1/whoami", cookies_file="/tmp/debug_auth_cookies.txt"
    )

    if result and result.returncode == 0:
        try:
            response_data = json.loads(result.stdout)
            if response_data.get("is_authenticated"):
                print("✅ Authentication persisted!")
                print(f"👤 User ID: {response_data.get('user_id', 'N/A')}")
                print(f"🎯 Source: {response_data.get('source', 'N/A')}")
            else:
                print("❌ Authentication not persisted")
                print(f"Response: {response_data}")
        except:
            print(f"⚠️  Could not parse whoami response: {result.stdout[:200]}...")
    else:
        print("❌ Whoami request failed")

    # Step 5: Cookie Analysis
    print("\n🍪 STEP 5: COOKIE ANALYSIS")
    try:
        with open("/tmp/debug_auth_cookies.txt") as f:
            cookies_content = f.read()
            print("📋 Stored Cookies:")
            for line in cookies_content.split("\n"):
                if line and not line.startswith("#") and "\t" in line:
                    parts = line.split("\t")
                    if len(parts) >= 6:
                        domain, flag, path, secure, expiry, name = parts[:6]
                        value = parts[6] if len(parts) > 6 else ""
                        print(
                            f"  🍪 {name} = {value[:30]}{'...' if len(value) > 30 else ''}"
                        )
    except Exception as e:
        print(f"⚠️  Could not read cookies: {e}")

    print(f"\n🎉 DEBUG COMPLETE - {datetime.now(UTC).isoformat()}")


if __name__ == "__main__":
    main()
