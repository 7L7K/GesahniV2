#!/usr/bin/env python3
"""
Test script to demonstrate authentication diagnostic logs
"""
import os
import requests
import subprocess
import time
import signal

def test_auth_logs():
    print("🚀 Starting authentication diagnostic log test...")

    # Set environment variables for debug logging
    env = os.environ.copy()
    env['LOG_LEVEL'] = 'DEBUG'
    env['LOG_TO_STDOUT'] = '1'

    # Start the server in the background
    server_process = subprocess.Popen([
        'uvicorn', 'app.main:app',
        '--host', '0.0.0.0',
        '--port', '8000',
        '--reload'
    ], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    try:
        print("⏳ Waiting for server to start...")
        time.sleep(5)  # Give server time to start

        # Test 1: Login
        print("\n🔑 Test 1: Login")
        login_resp = requests.post('http://localhost:8000/v1/auth/login?username=testuser')
        print(f"   Status: {login_resp.status_code}")
        cookies = login_resp.cookies
        print(f"   Cookies: {list(cookies.keys())}")

        # Test 2: Whoami (should work)
        print("\n👤 Test 2: Whoami")
        whoami_resp = requests.get('http://localhost:8000/v1/whoami', cookies=cookies)
        print(f"   Status: {whoami_resp.status_code}")
        if whoami_resp.status_code == 200:
            data = whoami_resp.json()
            print(f"   Authenticated: {data.get('is_authenticated')}")
            print(f"   User ID: {data.get('user_id')}")
            print(f"   Source: {data.get('source')}")

        # Test 3: Refresh
        print("\n🔄 Test 3: Refresh")
        refresh_resp = requests.post('http://localhost:8000/v1/auth/refresh', cookies=cookies)
        print(f"   Status: {refresh_resp.status_code}")

        # Test 4: Invalid request (should show auth failure logs)
        print("\n❌ Test 4: Invalid request (no cookies)")
        invalid_resp = requests.get('http://localhost:8000/v1/whoami')
        print(f"   Status: {invalid_resp.status_code}")

        # Test 5: Expired token simulation (would need to wait 15 minutes for real test)
        print("\n⏰ Test 5: Note - For expired token test, wait 15 minutes then retry whoami")

        print("\n✅ Test completed! Check server logs above for diagnostic messages.")

    except Exception as e:
        print(f"❌ Error during test: {e}")
    finally:
        # Stop the server
        print("\n🛑 Stopping server...")
        server_process.terminate()
        server_process.wait()

if __name__ == "__main__":
    test_auth_logs()
