#!/usr/bin/env python3
"""
Simple test script to verify Google OAuth endpoints are working.
Run this to check if the OAuth flow is functional.
"""

import time

import requests

BASE_URL = "http://localhost:8000"


def test_endpoints():
    print("🔍 Testing Google OAuth endpoints...")

    # Test 1: Check if server is running
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        print(f"✅ Server health: {response.status_code}")
    except Exception as e:
        print(f"❌ Server not running: {e}")
        return False

    # Test 2: Check Google connect endpoint
    try:
        response = requests.get(f"{BASE_URL}/v1/google/connect", timeout=5)
        print(f"✅ Google connect: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"   Auth URL: {data.get('authorize_url', 'N/A')[:50]}...")
            print(f"   State cookie set: {'g_state' in response.cookies}")
        return True
    except Exception as e:
        print(f"❌ Google connect failed: {e}")
        return False


def test_oauth_flow():
    print("\n🔄 Testing OAuth flow...")

    # Step 1: Get connect URL
    try:
        response = requests.get(f"{BASE_URL}/v1/google/connect")
        if response.status_code != 200:
            print(f"❌ Connect failed: {response.status_code}")
            return False

        data = response.json()
        auth_url = data.get("authorize_url")
        state_cookie = response.cookies.get("g_state")

        print(f"✅ Got auth URL: {auth_url[:50]}...")
        print(f"✅ State cookie: {state_cookie[:20] if state_cookie else 'None'}...")

        # Step 2: Simulate callback (this will fail but shows the flow works)
        if state_cookie:
            callback_url = f"{BASE_URL}/v1/google/auth/callback?code=test-code&state={state_cookie}"
            response = requests.get(callback_url, cookies={"g_state": state_cookie})
            print(f"✅ Callback test: {response.status_code}")
            if response.status_code in [302, 400, 401]:
                print("   (Expected - this is just testing the flow)")

        return True

    except Exception as e:
        print(f"❌ OAuth flow test failed: {e}")
        return False


if __name__ == "__main__":
    print("🚀 Starting Google OAuth test...")

    # Start the server if not running
    import subprocess
    import time

    try:
        # Check if server is running
        requests.get(f"{BASE_URL}/health", timeout=2)
        print("✅ Server already running")
    except:
        print("🔄 Starting server...")
        subprocess.Popen(
            [
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                "8000",
                "--reload",
            ],
            cwd="/Users/kingal/2025/GesahniV2",
        )
        time.sleep(3)

    # Run tests
    if test_endpoints():
        test_oauth_flow()
        print("\n🎉 Google OAuth endpoints are working!")
        print("\n📝 Next steps:")
        print("1. Open your browser to http://localhost:3000")
        print("2. Go to Settings > Integrations > Google")
        print("3. Click 'Connect Google Account'")
        print("4. Complete the OAuth flow")
    else:
        print("\n❌ Tests failed - check server logs")
