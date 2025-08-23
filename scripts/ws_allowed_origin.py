#!/usr/bin/env python3
"""Connect to the local server websocket `/v1/ws/health` with an allowed Origin header
and print the messages and close behavior.
"""
import asyncio
import websockets

URI = "ws://127.0.0.1:8000/v1/ws/health"
HEADERS = {"Origin": "http://localhost:3000"}


async def run():
    print(f"Connecting to {URI} with allowed Origin")
    async with websockets.connect(URI, extra_headers=HEADERS) as ws:
        try:
            msg = await ws.recv()
            print("Received:", msg)
        except Exception as e:
            print("Error receiving:", e)


if __name__ == "__main__":
    asyncio.run(run())


