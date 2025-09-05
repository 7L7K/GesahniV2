#!/usr/bin/env python3
"""Direct test script for idempotency functionality using requests."""

import requests
import json

def test_idempotency():
    base_url = "http://127.0.0.1:8000"

    print("=== Testing Idempotency DoD ===")
    print()

    # First request
    print("1. First request with Idempotency-Key abc123:")
    headers1 = {
        'content-type': 'application/json',
        'Idempotency-Key': 'abc123'
    }
    data1 = {'prompt': 'hi'}

    try:
        response1 = requests.post(f"{base_url}/v1/ask", headers=headers1, json=data1, timeout=10)
        print(f"   Status: {response1.status_code}")
        print(f"   Response: {response1.text}")
        if response1.status_code == 200:
            try:
                data1_parsed = response1.json()
                req_id_1 = data1_parsed.get('req_id', 'unknown')
                print(f"   Request ID: {req_id_1}")
                response1_text = response1.text
            except:
                req_id_1 = 'unknown'
                response1_text = response1.text
        else:
            print(f"   Error: HTTP {response1.status_code}")
            return
    except Exception as e:
        print(f"   Error: {e}")
        return

    print()

    # Second request with same key
    print("2. Second request with SAME Idempotency-Key abc123:")
    headers2 = {
        'content-type': 'application/json',
        'Idempotency-Key': 'abc123'
    }
    data2 = {'prompt': 'hi'}

    try:
        response2 = requests.post(f"{base_url}/v1/ask", headers=headers2, json=data2, timeout=10)
        print(f"   Status: {response2.status_code}")
        print(f"   Response: {response2.text}")
        if response2.status_code == 200:
            try:
                data2_parsed = response2.json()
                req_id_2 = data2_parsed.get('req_id', 'unknown')
                print(f"   Request ID: {req_id_2}")
                response2_text = response2.text
            except:
                req_id_2 = 'unknown'
                response2_text = response2.text
        else:
            print(f"   Error: HTTP {response2.status_code}")
            return
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
        print(f"   First:  {response1.text}")
        print(f"   Second: {response2.text}")

    print()
    print("3. Third request with DIFFERENT Idempotency-Key xyz789:")
    headers3 = {
        'content-type': 'application/json',
        'Idempotency-Key': 'xyz789'
    }
    data3 = {'prompt': 'hi'}

    try:
        response3 = requests.post(f"{base_url}/v1/ask", headers=headers3, json=data3, timeout=10)
        print(f"   Status: {response3.status_code}")
        print(f"   Response: {response3.text}")
        if response3.status_code == 200:
            try:
                data3_parsed = response3.json()
                req_id_3 = data3_parsed.get('req_id', 'unknown')
                print(f"   Request ID: {req_id_3}")
            except:
                pass
    except Exception as e:
        print(f"   Error: {e}")

if __name__ == "__main__":
    test_idempotency()
