#!/usr/bin/env python3
"""Connect to the local server websocket `/v1/ws/health` with a disallowed Origin header
and print close / error behavior.
"""
import asyncio

import websockets

URI = "ws://127.0.0.1:8000/v1/ws/health"
HEADERS = {"Origin": "https://evil.example"}


async def run():
    print(f"Connecting to {URI} with disallowed Origin")
    try:
        async with websockets.connect(URI, extra_headers=HEADERS) as ws:
            # Attempt to receive; server should close with 4403 or connection refused
            msg = await ws.recv()
            print("Received:", msg)
    except Exception as e:
        print("Connection failed / closed:", repr(e))


if __name__ == "__main__":
    asyncio.run(run())
