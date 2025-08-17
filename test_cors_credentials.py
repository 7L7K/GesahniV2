#!/usr/bin/env python3

import asyncio
import httpx
import json

async def test_cors_with_credentials():
    async with httpx.AsyncClient() as client:
        # Test 1: GET request with Origin header and credentials
        print("Test 1: GET request with Origin header and credentials")
        response = await client.get(
            "http://127.0.0.1:8000/healthz/ready",
            headers={"Origin": "http://localhost:3000"},
            cookies={"test_cookie": "test_value"}
        )
        print(f"Status: {response.status_code}")
        print(f"CORS Headers:")
        for key, value in response.headers.items():
            if key.lower().startswith('access-control'):
                print(f"  {key}: {value}")
        
        # Test 2: OPTIONS preflight request with credentials
        print("\nTest 2: OPTIONS preflight request with credentials")
        response = await client.options(
            "http://127.0.0.1:8000/healthz/ready",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "content-type",
                "Access-Control-Request-Credentials": "true"
            }
        )
        print(f"Status: {response.status_code}")
        print(f"CORS Headers:")
        for key, value in response.headers.items():
            if key.lower().startswith('access-control'):
                print(f"  {key}: {value}")

if __name__ == "__main__":
    asyncio.run(test_cors_with_credentials())
