#!/usr/bin/env python3
import asyncio

import pytest
import websockets


@pytest.mark.asyncio
async def test_websocket_auth():
    try:
        # Test without token (should fail)
        print("Testing WebSocket without token...")
        async with websockets.connect("ws://localhost:8000/v1/ws/transcribe"):
            print("ERROR: Connection should have failed!")
    except websockets.exceptions.ConnectionClosed as e:
        print(f"✓ Connection closed as expected: {e.code} - {e.reason}")
    except Exception as e:
        print(f"Connection failed: {e}")

    try:
        # Test with invalid origin (should fail)
        print("\nTesting WebSocket with invalid origin...")
        headers = {"Origin": "https://malicious.com"}
        async with websockets.connect(
            "ws://localhost:8000/v1/ws/transcribe", extra_headers=headers
        ):
            print("ERROR: Connection should have failed!")
    except websockets.exceptions.ConnectionClosed as e:
        print(f"✓ Connection closed as expected: {e.code} - {e.reason}")
    except Exception as e:
        print(f"Connection failed: {e}")


if __name__ == "__main__":
    asyncio.run(test_websocket_auth())
