#!/usr/bin/env python3
"""
Spotify Integration Test Script

This script demonstrates how to use the Spotify debugger effectively
instead of adding random log statements throughout the code.

Usage:
    python test_spotify_integration.py
"""

import asyncio
import os

from fastapi import FastAPI
from fastapi.testclient import TestClient

# Import the Spotify debugger
from spotify_debugger import (
    create_debug_routes,
    debug_log_spotify_request,
    debug_log_spotify_response,
    debug_spotify_integration,
    debug_track_spotify_operation,
)


async def test_spotify_status_endpoint():
    """Test the Spotify status endpoint with debugging."""
    print("🧪 Testing Spotify Status Endpoint with Debugging")

    # Log the request
    debug_log_spotify_request(
        operation="test_spotify_status",
        user_id="test_user",
        endpoint="/v1/spotify/status",
        test_mode=True,
    )

    # Set up test environment
    os.environ["TEST_MODE"] = "1"
    os.environ["JWT_OPTIONAL_IN_TESTS"] = "1"

    try:
        from app.main import app

        client = TestClient(app)

        # Track the operation with timing
        async with debug_track_spotify_operation("spotify_status_test", "test_user"):
            response = client.get("/v1/spotify/status")
            print(f"  Status Code: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                print(f"  Response: {data}")
                debug_log_spotify_response(
                    operation="test_spotify_status",
                    user_id="test_user",
                    status="success",
                    response_data=data,
                )
            else:
                print(f"  Error: {response.text}")
                debug_log_spotify_response(
                    operation="test_spotify_status",
                    user_id="test_user",
                    status="error",
                    error=f"HTTP {response.status_code}: {response.text}",
                )

    except Exception as e:
        print(f"  Exception: {e}")
        debug_log_spotify_response(
            operation="test_spotify_status",
            user_id="test_user",
            status="error",
            error=str(e),
        )


async def test_spotify_auth_flow():
    """Test Spotify authentication flow."""
    print("\n🔐 Testing Spotify Auth Flow")

    os.environ["TEST_MODE"] = "1"
    os.environ["JWT_OPTIONAL_IN_TESTS"] = "1"

    try:
        from app.main import app

        client = TestClient(app)

        # Test login endpoint (should return 422 for missing user_id)
        async with debug_track_spotify_operation("spotify_login_test", "test_user"):
            response = client.get("/v1/spotify/login")
            print(
                f"  Login endpoint: {response.status_code} (expected: 422 - validation error)"
            )

        # Test callback endpoint (should return 400 for missing params)
        async with debug_track_spotify_operation("spotify_callback_test", "test_user"):
            response = client.get("/v1/spotify/callback")
            print(
                f"  Callback endpoint: {response.status_code} (expected: 400 - missing params)"
            )

    except Exception as e:
        print(f"  Exception: {e}")


async def test_spotify_debug_routes():
    """Test the Spotify debug routes."""
    print("\n🔧 Testing Spotify Debug Routes")

    # Create a test app with debug routes
    app = FastAPI()
    create_debug_routes(app)

    client = TestClient(app)

    # Test health endpoint
    response = client.get("/debug/spotify/health")
    print(f"  Health endpoint: {response.status_code}")
    if response.status_code == 200:
        health_data = response.json()
        print(f"  Health status: {health_data}")

    # Test stats endpoint
    response = client.get("/debug/spotify/stats")
    print(f"  Stats endpoint: {response.status_code}")

    # Test events endpoint
    response = client.get("/debug/spotify/events")
    print(f"  Events endpoint: {response.status_code}")
    if response.status_code == 200:
        events = response.json()
        print(f"  Recent events: {len(events)}")


async def demonstrate_debugging_workflow():
    """Demonstrate the complete debugging workflow."""
    print("🚀 Spotify Integration Debugging Workflow")
    print("=" * 50)

    # Step 1: Run health checks
    print("\n📊 Step 1: Health Checks")
    await debug_spotify_integration()

    # Step 2: Test endpoints with structured debugging
    print("\n🔍 Step 2: Testing Endpoints")
    await test_spotify_status_endpoint()
    await test_spotify_auth_flow()

    # Step 3: Show debug routes
    print("\n🔧 Step 3: Debug Routes")
    await test_spotify_debug_routes()

    # Step 4: Show final debug report
    print("\n📈 Step 4: Final Debug Report")
    await debug_spotify_integration()


def demonstrate_code_integration():
    """Show how to integrate debugging into actual Spotify code."""
    print("\n💻 Code Integration Examples")
    print("=" * 30)

    example_code = """
# Instead of this (random logging):
def old_way():
    print("Starting Spotify operation...")
    # ... do something ...
    print("Spotify operation completed")

# Use this (structured debugging):
async def new_way(user_id: str):
    async with debug_track_spotify_operation("spotify_operation", user_id):
        debug_log_spotify_request("spotify_operation", user_id, extra_data="...")
        try:
            # ... actual Spotify code ...
            result = await spotify_client.get_currently_playing()
            debug_log_spotify_response("spotify_operation", user_id, status="success", track=result)
            return result
        except Exception as e:
            debug_log_spotify_response("spotify_operation", user_id, status="error", error=str(e))
            raise

# In your main app, add debug routes:
from spotify_debugger import create_debug_routes
create_debug_routes(app)

# Now you can monitor via:
# GET /debug/spotify/health
# GET /debug/spotify/events
# GET /debug/spotify/stats
"""

    print(example_code)


async def main():
    """Run all Spotify integration tests."""
    print("🎵 Spotify Integration Comprehensive Test")
    print("=" * 50)

    # Run the debugging workflow
    await demonstrate_debugging_workflow()

    # Show code integration examples
    demonstrate_code_integration()

    print("\n✅ Test complete!")
    print("\n📚 Key Benefits of this approach:")
    print("  • Structured, searchable debug events")
    print("  • Automatic timing and error tracking")
    print("  • Health checks for proactive monitoring")
    print("  • Debug routes for runtime inspection")
    print("  • Clean separation from business logic")
    print("  • No need for random print statements!")


if __name__ == "__main__":
    asyncio.run(main())
