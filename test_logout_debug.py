#!/usr/bin/env python3
"""
Enhanced logout testing script with detailed logging
This script tests the logout functionality end-to-end
"""
import requests
import time
import json

def test_logout_flow():
    """Test complete logout flow with detailed logging"""
    base_url = "http://localhost:8000"

    print("🔍 LOGOUT TEST: Starting comprehensive logout test")
    print("=" * 80)

    # Step 1: Login to get tokens
    print("\n1️⃣ LOGIN PHASE:")
    login_payload = {"username": "testuser", "password": "testpass"}
    login_url = f"{base_url}/v1/auth/login?username=testuser"

    print(f"   POST {login_url}")
    print(f"   Payload: {json.dumps(login_payload, indent=2)}")

    try:
        login_response = requests.post(login_url, json=login_payload)
        print(f"   Response Status: {login_response.status_code}")
        print(f"   Response Headers: {dict(login_response.headers)}")

        if login_response.status_code == 200:
            print("   ✅ Login successful")

            # Extract cookies
            cookies = login_response.cookies
            print(f"   Cookies received: {dict(cookies)}")

            # Step 2: Check whoami endpoint
            print("\n2️⃣ WHOAMI CHECK:")
            whoami_url = f"{base_url}/v1/auth/whoami"
            print(f"   GET {whoami_url}")

            whoami_response = requests.get(whoami_url, cookies=cookies)
            print(f"   Response Status: {whoami_response.status_code}")
            if whoami_response.status_code == 200:
                print("   ✅ Whoami successful - user is authenticated")
            else:
                print("   ❌ Whoami failed - user not authenticated")

            # Step 3: Logout
            print("\n3️⃣ LOGOUT PHASE:")
            logout_url = f"{base_url}/v1/auth/logout"
            print(f"   POST {logout_url}")

            logout_response = requests.post(logout_url, cookies=cookies)
            print(f"   Response Status: {logout_response.status_code}")
            print(f"   Response Headers: {dict(logout_response.headers)}")

            if logout_response.status_code == 204:
                print("   ✅ Logout successful - 204 No Content")
            else:
                print(f"   ❌ Logout failed - Status: {logout_response.status_code}")

            # Step 4: Verify logout by checking whoami again
            print("\n4️⃣ VERIFICATION PHASE:")
            print(f"   GET {whoami_url} (should fail now)")

            verification_response = requests.get(whoami_url, cookies=cookies)
            print(f"   Response Status: {verification_response.status_code}")

            if verification_response.status_code == 401:
                print("   ✅ Verification successful - user properly logged out")
            else:
                print(f"   ❌ Verification failed - user still authenticated (Status: {verification_response.status_code})")

        else:
            print(f"   ❌ Login failed with status: {login_response.status_code}")
            print(f"   Response: {login_response.text}")

    except requests.exceptions.RequestException as e:
        print(f"   ❌ Request failed: {e}")

    print("\n" + "=" * 80)
    print("🔍 LOGOUT TEST: Complete")

if __name__ == "__main__":
    test_logout_flow()
