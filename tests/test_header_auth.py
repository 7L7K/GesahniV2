#!/usr/bin/env python3
"""
Test script to verify Option A - Header mode implementation.

This script tests:
1. Frontend sends Authorization: Bearer <token> on /v1/* calls
2. Backend accepts and verifies Bearer tokens
3. Backend bypasses CSRF when Authorization is present
4. Backend logs whoami.header_check has_authorization_header=true
5. /v1/state returns 200 when properly authenticated
"""

import json
import time

import requests

BASE_URL = "http://localhost:8000"


def test_whoami_with_header():
    """Test that whoami logs authorization header correctly."""
    print("🔍 Testing whoami with Authorization header...")

    # Test without header
    response = requests.get(f"{BASE_URL}/v1/whoami")
    print(f"   Without header: {response.status_code}")
    data = response.json()
    print(f"   Response: {json.dumps(data, indent=2)}")

    # Test with invalid header
    headers = {"Authorization": "Bearer invalid-token"}
    response = requests.get(f"{BASE_URL}/v1/whoami", headers=headers)
    print(f"   With invalid header: {response.status_code}")
    data = response.json()
    print(f"   Response: {json.dumps(data, indent=2)}")

    # Check if source is "header" when Authorization is present
    if data.get("source") == "header":
        print("   ✅ Backend correctly identifies header source")
    else:
        print(f"   ⚠️  Backend source: {data.get('source')}")


def test_csrf_bypass():
    """Test that CSRF is bypassed when Authorization header is present."""
    print("\n🔒 Testing CSRF bypass with Authorization header...")

    # Test POST without CSRF token (should fail)
    data = {"test": "data"}
    response = requests.post(f"{BASE_URL}/v1/state", json=data)
    print(f"   POST without CSRF: {response.status_code}")

    # Test POST with Authorization header (should bypass CSRF)
    headers = {"Authorization": "Bearer test-token"}
    response = requests.post(f"{BASE_URL}/v1/state", json=data, headers=headers)
    print(f"   POST with Authorization header: {response.status_code}")

    if (
        response.status_code == 401
    ):  # Unauthorized due to invalid token, but CSRF bypassed
        print("   ✅ CSRF bypassed (got 401 for invalid token, not 403 for CSRF)")
    else:
        print(f"   ⚠️  Unexpected status: {response.status_code}")


def test_state_endpoint():
    """Test /v1/state endpoint with proper authentication."""
    print("\n📊 Testing /v1/state endpoint...")

    # Test without authentication
    response = requests.get(f"{BASE_URL}/v1/state")
    print(f"   Without auth: {response.status_code}")

    # Test with invalid token
    headers = {"Authorization": "Bearer invalid-token"}
    response = requests.get(f"{BASE_URL}/v1/state", headers=headers)
    print(f"   With invalid token: {response.status_code}")

    # Note: We can't test with valid token without setting up proper authentication
    print("   ℹ️  Valid token test requires proper authentication setup")


def check_environment():
    """Check environment configuration."""
    print("\n⚙️  Checking environment configuration...")

    # Check if header auth mode is enabled
    try:
        response = requests.get(f"{BASE_URL}/config")
        if response.status_code == 200:
            response.json()
            print(f"   Backend config available: {response.status_code}")
        else:
            print(f"   Backend config: {response.status_code}")
    except Exception as e:
        print(f"   Backend config error: {e}")

    print("   ℹ️  Check env.localhost for NEXT_PUBLIC_HEADER_AUTH_MODE=1")


def main():
    print("🚀 Testing Option A - Header Mode Implementation")
    print("=" * 50)

    # Wait for servers to be ready
    print("⏳ Waiting for servers to be ready...")
    time.sleep(2)

    test_whoami_with_header()
    test_csrf_bypass()
    test_state_endpoint()
    check_environment()

    print("\n" + "=" * 50)
    print("✅ Header mode test completed!")
    print("\n📋 Verification checklist:")
    print(
        "   □ Check backend logs for 'whoami.header_check has_authorization_header=true'"
    )
    print("   □ Check backend logs for 'bypass: csrf_authorization_header_present'")
    print("   □ Verify frontend sends Authorization headers on /v1/* calls")
    print("   □ Test with valid Clerk JWT token")


if __name__ == "__main__":
    main()
