#!/usr/bin/env python3
"""Spotify integration debugging script."""

import importlib
import logging
import os

from fastapi.testclient import TestClient

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def test_spotify_imports():
    """Test if Spotify modules can be imported successfully."""
    print("=== Testing Spotify Module Imports ===")

    modules_to_test = [
        ("app.api.spotify", "Spotify OAuth router"),
        ("app.api.spotify_player", "Spotify player router"),
        ("app.api.spotify_sdk", "Spotify SDK router"),
        ("app.integrations.spotify.client", "Spotify client"),
        ("app.integrations.spotify.oauth", "Spotify OAuth"),
    ]

    for module_path, description in modules_to_test:
        try:
            importlib.import_module(module_path)
            print(f"✓ {description}: {module_path} - OK")
        except ImportError as e:
            print(f"✗ {description}: {module_path} - FAILED: {e}")
        except Exception as e:
            print(f"✗ {description}: {module_path} - ERROR: {e}")

def test_router_creation():
    """Test if routers can be created successfully."""
    print("\n=== Testing Router Creation ===")

    try:
        from app.api.spotify import router as spotify_router
        print(f"✓ Spotify router created: {len(spotify_router.routes)} routes")
        for route in spotify_router.routes:
            print(f"  - {route.methods} {route.path}")
    except Exception as e:
        print(f"✗ Spotify router creation failed: {e}")

    try:
        from app.api.spotify_player import router as player_router
        print(f"✓ Spotify player router created: {len(player_router.routes)} routes")
        for route in player_router.routes:
            print(f"  - {route.methods} {route.path}")
    except Exception as e:
        print(f"✗ Spotify player router creation failed: {e}")

    try:
        from app.api.spotify_sdk import router as sdk_router
        print(f"✓ Spotify SDK router created: {len(sdk_router.routes)} routes")
        for route in sdk_router.routes:
            print(f"  - {route.methods} {route.path}")
    except Exception as e:
        print(f"✗ Spotify SDK router creation failed: {e}")

def test_main_app_router_registration():
    """Test if routers are registered in main app."""
    print("\n=== Testing Main App Router Registration ===")

    # Set test environment
    os.environ['TEST_MODE'] = '1'
    os.environ['JWT_OPTIONAL_IN_TESTS'] = '1'

    try:
        from app.main import app
        print("✓ Main app created successfully")
        # Check if routes are registered
        spotify_routes = [route for route in app.routes if 'spotify' in str(route.path)]
        print(f"✓ Found {len(spotify_routes)} Spotify-related routes:")
        for route in spotify_routes:
            print(f"  - {route.methods} {route.path}")

        # Test specific endpoints
        test_client = TestClient(app)

        endpoints_to_test = [
            "/v1/spotify/status",
            "/v1/spotify/login",
            "/v1/spotify/connect",
            "/v1/spotify/callback",
            "/v1/spotify/devices",
            "/v1/spotify/play",
            "/v1/spotify/token-for-sdk"
        ]

        print("\n--- Testing Endpoints ---")
        for endpoint in endpoints_to_test:
            try:
                response = test_client.get(endpoint)
                print(f"✓ {endpoint}: {response.status_code}")
            except Exception as e:
                print(f"✗ {endpoint}: ERROR - {e}")

    except Exception as e:
        print(f"✗ Main app creation failed: {e}")

def test_spotify_config():
    """Test Spotify configuration."""
    print("\n=== Testing Spotify Configuration ===")

    required_vars = [
        "SPOTIFY_CLIENT_ID",
        "SPOTIFY_CLIENT_SECRET",
    ]

    for var in required_vars:
        value = os.getenv(var)
        if value:
            print(f"✓ {var}: Set (length: {len(value)})")
        else:
            print(f"✗ {var}: NOT SET")

def main():
    """Run all Spotify debugging tests."""
    print("Spotify Integration Debug Report")
    print("=" * 50)

    test_spotify_imports()
    test_router_creation()
    test_main_app_router_registration()
    test_spotify_config()

    print("\n" + "=" * 50)
    print("Debug report complete. Check for any FAILED items above.")

if __name__ == "__main__":
    main()
