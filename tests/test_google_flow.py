#!/usr/bin/env python3
import requests
import json

BASE_URL = "http://localhost:8000"


def test_google_oauth_flow():
    print("🧪 Testing Google OAuth Flow...")

    # Test 1: OAuth URL generation
    print("\n1. Testing OAuth URL generation...")
    response = requests.get(f"{BASE_URL}/v1/google/auth/login_url?next=/settings")
    if response.status_code == 200:
        data = response.json()
        url = data.get("url", "")
        print("   ✅ OAuth URL generated successfully")
        print(f"   📏 URL length: {len(url)} characters")

        # Check required parameters
        from urllib.parse import urlparse, parse_qs

        parsed = urlparse(url)
        params = parse_qs(parsed.query)

        checks = [
            ("client_id" in params, "client_id parameter"),
            ("redirect_uri" in params, "redirect_uri parameter"),
            ("scope" in params, "scope parameter"),
            ("state" in params, "state parameter"),
            (
                "redirect_params" in params
                and "next=" in params.get("redirect_params", [""])[0],
                "next parameter",
            ),
        ]

        for check, desc in checks:
            print(f"   {'✅' if check else '❌'} {desc}")

        if all(check for check, _ in checks):
            print("   🎉 All OAuth parameters present!")
        else:
            print("   ⚠️  Some OAuth parameters missing!")
    else:
        print(f"   ❌ Failed to generate OAuth URL: {response.status_code}")
        return False

    # Test 2: Check CSRF cookies
    print("\n2. Checking CSRF protection...")
    cookies = response.cookies
    has_g_state = any("g_state" in cookie.name for cookie in cookies)
    has_g_next = any("g_next" in cookie.name for cookie in cookies)

    print(f"   {'✅' if has_g_state else '❌'} g_state cookie set")
    print(f"   {'✅' if has_g_next else '❌'} g_next cookie set")

    if has_g_state and has_g_next:
        print("   🔒 CSRF protection active!")
    else:
        print("   ⚠️  CSRF protection may be missing!")

    # Test 3: Test callback validation
    print("\n3. Testing callback validation...")
    callback_response = requests.get(
        f"{BASE_URL}/v1/google/auth/callback?state=invalid&code=invalid"
    )
    if callback_response.status_code == 400:
        print("   ✅ Callback properly rejects invalid parameters")
    else:
        print(f"   ⚠️  Callback returned {callback_response.status_code} (expected 400)")

    # Test 4: Test status endpoint authentication
    print("\n4. Testing Google status endpoint...")
    status_response = requests.get(
        f"{BASE_URL}/v1/google/status", headers={"Authorization": "Bearer invalid"}
    )
    if status_response.status_code == 401:
        print("   ✅ Status endpoint properly requires authentication")
    else:
        print(
            f"   ⚠️  Status endpoint returned {status_response.status_code} (expected 401)"
        )

    # Test 5: Test integrations status endpoint
    print("\n5. Testing integrations status endpoint...")
    integrations_response = requests.get(f"{BASE_URL}/v1/integrations/status")
    if integrations_response.status_code == 200:
        data = integrations_response.json()
        google_status = data.get("google", {}).get("status", "unknown")
        print(f"   ✅ Integrations status: Google is '{google_status}'")
        print("   📊 Full status:", json.dumps(data, indent=2))
    else:
        print(
            f"   ❌ Failed to get integrations status: {integrations_response.status_code}"
        )

    print("\n🎯 Google OAuth Flow Test Complete!")
    return True


if __name__ == "__main__":
    test_google_oauth_flow()
