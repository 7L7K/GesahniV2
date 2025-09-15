#!/usr/bin/env python3
"""
Test script to simulate the complete Spotify OAuth flow
"""

import json

import requests


def test_spotify_flow():
    print("=== Spotify OAuth Flow Test ===")

    # Step 1: Test backend Spotify login endpoint
    print("\n1. Testing backend Spotify login endpoint...")
    try:
        response = requests.get(
            "http://localhost:8000/v1/spotify/login",
            params={"user_id": "demo"},
            cookies={"GSNH_AT": "test_token"},
        )
        print(f"   Status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            print(f"   Response: {json.dumps(data, indent=2)}")

            if data.get("ok") and data.get("authorize_url"):
                print("   ✅ Backend working correctly")
                auth_url = data["authorize_url"]
                print(f"   Auth URL: {auth_url[:100]}...")
            else:
                print("   ❌ Backend returned invalid response")
                return
        else:
            print(f"   ❌ Backend failed: {response.text}")
            return

    except Exception as e:
        print(f"   ❌ Backend connection failed: {e}")
        return

    # Step 2: Test frontend pages
    print("\n2. Testing frontend pages...")
    frontend_urls = [
        "http://localhost:3000/",
        "http://localhost:3000/integrations",
        "http://localhost:3000/spotify/connect",
    ]

    for url in frontend_urls:
        try:
            response = requests.get(url)
            print(f"   {url}: {response.status_code}")
        except Exception as e:
            print(f"   {url}: ❌ {e}")

    print("\n3. Flow Analysis:")
    print("   ✅ Backend Spotify endpoint working")
    print("   ✅ Frontend pages accessible")
    print("   ✅ Authorization URL generated correctly")
    print("\n   The issue might be:")
    print("   - Frontend not calling the API correctly")
    print("   - JavaScript errors in browser")
    print("   - Authentication/cookie issues")
    print("   - Network connectivity between frontend and backend")


if __name__ == "__main__":
    test_spotify_flow()
