#!/usr/bin/env python3
"""Test script for idempotency functionality."""

import requests
import json
import time

def test_idempotency():
    base_url = "http://127.0.0.1:8000"
    headers = {
        'content-type': 'application/json',
        'Idempotency-Key': 'abc123'
    }
    data = {'prompt': 'hi'}

    print("=== Testing Idempotency DoD ===")
    print()

    # First request
    print("1. First request with Idempotency-Key abc123:")
    try:
        response1 = requests.post(f"{base_url}/v1/ask", headers=headers, json=data, timeout=10)
        print(f"   Status: {response1.status_code}")
        print(f"   Response: {response1.text}")
        if response1.status_code == 200:
            response1_data = response1.json()
            req_id_1 = response1_data.get('req_id', 'unknown')
            print(f"   Request ID: {req_id_1}")
    except Exception as e:
        print(f"   Error: {e}")
        return

    print()

    # Wait a moment
    time.sleep(1)

    # Second request with same key
    print("2. Second request with SAME Idempotency-Key abc123:")
    try:
        response2 = requests.post(f"{base_url}/v1/ask", headers=headers, json=data, timeout=10)
        print(f"   Status: {response2.status_code}")
        print(f"   Response: {response2.text}")
        if response2.status_code == 200:
            response2_data = response2.json()
            req_id_2 = response2_data.get('req_id', 'unknown')
            print(f"   Request ID: {req_id_2}")
    except Exception as e:
        print(f"   Error: {e}")
        return

    print()

    # Check if responses are identical
    if response1.status_code == response2.status_code and response1.text == response2.text:
        print("✅ SUCCESS: Both responses are identical!")
        print("   This confirms idempotency is working correctly.")
    else:
        print("❌ FAILURE: Responses are different!")
        print("   Idempotency is not working as expected.")

    print()
    print("3. Third request with DIFFERENT Idempotency-Key xyz789:")
    headers3 = headers.copy()
    headers3['Idempotency-Key'] = 'xyz789'
    try:
        response3 = requests.post(f"{base_url}/v1/ask", headers=headers3, json=data, timeout=10)
        print(f"   Status: {response3.status_code}")
        print(f"   Response: {response3.text}")
        if response3.status_code == 200:
            response3_data = response3.json()
            req_id_3 = response3_data.get('req_id', 'unknown')
            print(f"   Request ID: {req_id_3}")
    except Exception as e:
        print(f"   Error: {e}")

if __name__ == "__main__":
    test_idempotency()
