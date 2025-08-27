#!/usr/bin/env python3
"""
Debug script to test frontend-to-backend Spotify communication
"""
import asyncio
import json
import os
import sys

# Add current directory to path
sys.path.append('.')

async def test_frontend_api_call():
    """Test the frontend API call simulation"""
    print("=== Frontend API Call Debug ===")

    try:
        # Import the API fetch function
        sys.path.append('frontend/src/lib')
        from app.lib.api import apiFetch

        print("✅ API module imported successfully")

        # Test the API call (this would normally happen in browser)
        print("\n1. Testing API call simulation...")

        # Simulate the frontend call that happens when clicking connect
        base_url = "http://localhost:8000"
        path = "/v1/spotify/login"
        user_id = "demo"

        full_url = f"{base_url}{path}?user_id={user_id}"
        print(f"   URL: {full_url}")
        print("   Method: GET")
        print("   Credentials: include")
        print("   Auth: false")

        # Note: We can't actually call apiFetch from Python since it's designed for browser
        # But we can test the backend directly
        print("\n2. Testing backend directly...")
        import requests

        response = requests.get(
            full_url,
            cookies={"GSNH_AT": "test_token"}
        )

        print(f"   Backend Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"   Backend Response: {json.dumps(data, indent=2)}")
            print("   ✅ Backend communication working")
        else:
            print(f"   Backend Error: {response.text}")
            print("   ❌ Backend communication failed")

    except ImportError as e:
        print(f"❌ Could not import API module: {e}")
        print("   This suggests the frontend setup might have issues")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")

    print("\n=== Analysis ===")
    print("If backend is working but frontend isn't:")
    print("1. Check browser console for JavaScript errors")
    print("2. Check network tab for failed API calls")
    print("3. Verify frontend is running on correct port (3000)")
    print("4. Check if cookies are being sent properly")
    print("5. Verify CORS settings between frontend and backend")

if __name__ == "__main__":
    asyncio.run(test_frontend_api_call())
