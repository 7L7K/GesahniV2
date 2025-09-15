#!/usr/bin/env python3
"""
Test script to verify rate limiting improvements.
This script tests the auth orchestrator's rate limiting behavior.
"""

import asyncio
import json
import time

import aiohttp


async def test_whoami_rate_limiting():
    """Test whoami endpoint rate limiting behavior."""

    base_url = "http://localhost:8000"
    headers = {"Content-Type": "application/json", "Origin": "http://localhost:3000"}

    print("🧪 Testing whoami rate limiting...")

    async with aiohttp.ClientSession() as session:
        # Test 1: Single whoami call
        print("\n1. Testing single whoami call...")
        try:
            async with session.get(
                f"{base_url}/v1/whoami", headers=headers
            ) as response:
                print(f"   Status: {response.status}")
                if response.status == 200:
                    data = await response.json()
                    print(f"   Response: {json.dumps(data, indent=2)}")
                else:
                    print(f"   Error: {await response.text()}")
        except Exception as e:
            print(f"   Error: {e}")

        # Test 2: Multiple rapid calls (should be rate limited)
        print("\n2. Testing multiple rapid calls...")
        start_time = time.time()
        success_count = 0
        rate_limited_count = 0

        for i in range(10):
            try:
                async with session.get(
                    f"{base_url}/v1/whoami", headers=headers
                ) as response:
                    if response.status == 200:
                        success_count += 1
                        print(f"   Call {i+1}: Success")
                    elif response.status == 429:
                        rate_limited_count += 1
                        retry_after = response.headers.get("Retry-After", "unknown")
                        print(
                            f"   Call {i+1}: Rate limited (429) - Retry-After: {retry_after}"
                        )
                    else:
                        print(f"   Call {i+1}: Unexpected status {response.status}")
            except Exception as e:
                print(f"   Call {i+1}: Error - {e}")

            # Small delay between calls
            await asyncio.sleep(0.1)

        elapsed = time.time() - start_time
        print(
            f"\n   Results: {success_count} successful, {rate_limited_count} rate limited in {elapsed:.2f}s"
        )

        # Test 3: Check rate limit headers
        print("\n3. Testing rate limit headers...")
        try:
            async with session.get(
                f"{base_url}/v1/whoami", headers=headers
            ) as response:
                print(f"   Status: {response.status}")
                rate_limit_headers = {
                    "RateLimit-Limit": response.headers.get("RateLimit-Limit"),
                    "RateLimit-Remaining": response.headers.get("RateLimit-Remaining"),
                    "RateLimit-Reset": response.headers.get("RateLimit-Reset"),
                }
                print(f"   Rate limit headers: {rate_limit_headers}")
        except Exception as e:
            print(f"   Error: {e}")


async def test_health_endpoint():
    """Test health endpoint (should not be rate limited)."""

    base_url = "http://localhost:8000"
    headers = {"Content-Type": "application/json", "Origin": "http://localhost:3000"}

    print("\n🏥 Testing health endpoint...")

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(
                f"{base_url}/healthz/ready", headers=headers
            ) as response:
                print(f"   Status: {response.status}")
                if response.status == 200:
                    data = await response.json()
                    print(f"   Response: {json.dumps(data, indent=2)}")
                else:
                    print(f"   Error: {await response.text()}")
        except Exception as e:
            print(f"   Error: {e}")


async def main():
    """Run all tests."""
    print("🚀 Starting rate limiting tests...")

    # Test health endpoint first
    await test_health_endpoint()

    # Test whoami rate limiting
    await test_whoami_rate_limiting()

    print("\n✅ Rate limiting tests completed!")


if __name__ == "__main__":
    asyncio.run(main())
