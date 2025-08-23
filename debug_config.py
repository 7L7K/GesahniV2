#!/usr/bin/env python3
"""
Debug script to test configuration and CORS setup.
Run this to check if the backend is properly configured.
"""

import json
import os

import requests


def test_configuration():
    """Test the current configuration."""
    print("=== CONFIGURATION DEBUG ===")

    # Check environment variables
    env_vars = [
        "CORS_ALLOW_ORIGINS",
        "APP_URL",
        "API_URL",
        "HOST",
        "PORT",
        "CORS_ALLOW_CREDENTIALS",
        "NEXT_PUBLIC_API_ORIGIN",
    ]

    print("Environment variables:")
    for var in env_vars:
        value = os.getenv(var)
        print(f"  {var}: {repr(value)}")

    print("\n=== TESTING BACKEND CONNECTION ===")

    # Test backend connection
    try:
        backend_url = "http://localhost:8000"
        print(f"Testing connection to {backend_url}")

        # Test health endpoint
        health_response = requests.get(f"{backend_url}/healthz/ready", timeout=5)
        print(f"Health check: {health_response.status_code}")
        print(f"Health response: {health_response.text[:200]}")

        # Test debug config endpoint
        debug_response = requests.get(f"{backend_url}/debug/config", timeout=5)
        print(f"Debug config: {debug_response.status_code}")
        if debug_response.status_code == 200:
            config = debug_response.json()
            print("Backend configuration:")
            print(json.dumps(config, indent=2))

        # Test CORS preflight
        print("\n=== TESTING CORS ===")
        cors_response = requests.options(
            f"{backend_url}/v1/state",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "Content-Type",
            },
            timeout=5,
        )
        print(f"CORS preflight: {cors_response.status_code}")
        print(f"CORS headers: {dict(cors_response.headers)}")

        # Test actual request
        actual_response = requests.get(
            f"{backend_url}/v1/state",
            headers={"Origin": "http://localhost:3000"},
            timeout=5,
        )
        print(f"Actual request: {actual_response.status_code}")
        print(f"Response headers: {dict(actual_response.headers)}")

    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to backend. Is it running?")
        print("   Try: python -m app.main")
    except Exception as e:
        print(f"❌ Error testing backend: {e}")

    print("\n=== FRONTEND CONFIGURATION ===")

    # Check frontend environment
    frontend_env = "frontend/.env.local"
    if os.path.exists(frontend_env):
        print(f"Frontend environment file: {frontend_env}")
        with open(frontend_env) as f:
            content = f.read()
            for line in content.split("\n"):
                if "NEXT_PUBLIC_API_ORIGIN" in line:
                    print(f"  {line.strip()}")
    else:
        print(f"❌ Frontend environment file not found: {frontend_env}")

    print("\n=== RECOMMENDATIONS ===")
    print("1. Make sure backend is running: python -m app.main")
    print("2. Check that .env file has correct values")
    print("3. Verify frontend is using http://localhost:3000")
    print("4. Check browser console for CORS errors")


if __name__ == "__main__":
    test_configuration()
