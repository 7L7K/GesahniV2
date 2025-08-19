#!/usr/bin/env python3

import asyncio
import httpx
import json

async def test_cors():
    async with httpx.AsyncClient() as client:
        # Test 1: Simple GET request with Origin header
        print("Test 1: GET request with Origin header")
        response = await client.get(
            "http://localhost:8000/healthz/ready",
            headers={"Origin": "http://localhost:3000"}
        )
        print(f"Status: {response.status_code}")
        print(f"Headers: {dict(response.headers)}")
        
        # Test 2: OPTIONS preflight request
        print("\nTest 2: OPTIONS preflight request")
        response = await client.options(
            "http://localhost:8000/healthz/ready",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "content-type"
            }
        )
        print(f"Status: {response.status_code}")
        print(f"Headers: {dict(response.headers)}")
        
        # Test 3: Check if CORS headers are present
        print("\nTest 3: CORS headers analysis")
        cors_headers = {
            "access-control-allow-origin": response.headers.get("access-control-allow-origin"),
            "access-control-allow-methods": response.headers.get("access-control-allow-methods"),
            "access-control-allow-headers": response.headers.get("access-control-allow-headers"),
            "access-control-allow-credentials": response.headers.get("access-control-allow-credentials"),
        }
        print(f"CORS headers: {cors_headers}")

if __name__ == "__main__":
    asyncio.run(test_cors())
