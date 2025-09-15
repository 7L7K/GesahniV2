#!/usr/bin/env python3
"""Simple test script for idempotency functionality."""

import json
import subprocess


def run_curl(cmd):
    """Run curl command and return response."""
    try:
        # Use shell=False and pass command as list to avoid injection vulnerabilities
        result = subprocess.run(
            cmd if isinstance(cmd, list) else cmd.split(),
            shell=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.stdout.strip(), result.stderr.strip(), result.returncode
    except Exception as e:
        return "", str(e), 1


def test_idempotency():
    print("=== Testing Idempotency DoD ===")
    print()

    # First request
    print("1. First request with Idempotency-Key abc123:")
    cmd1 = 'curl -s -X POST localhost:8000/v1/ask -H "content-type: application/json" -H "Idempotency-Key: abc123" -d \'{"prompt":"hi"}\''
    stdout1, stderr1, code1 = run_curl(cmd1)

    if code1 == 0:
        print(f"   Response: {stdout1}")
        try:
            data1 = json.loads(stdout1)
            req_id_1 = data1.get("req_id", "unknown")
            print(f"   Request ID: {req_id_1}")
        except:
            req_id_1 = "unknown"
    else:
        print(f"   Error: {stderr1}")
        return

    print()

    # Second request with same key
    print("2. Second request with SAME Idempotency-Key abc123:")
    cmd2 = 'curl -s -X POST localhost:8000/v1/ask -H "content-type: application/json" -H "Idempotency-Key: abc123" -d \'{"prompt":"hi"}\''
    stdout2, stderr2, code2 = run_curl(cmd2)

    if code2 == 0:
        print(f"   Response: {stdout2}")
        try:
            data2 = json.loads(stdout2)
            req_id_2 = data2.get("req_id", "unknown")
            print(f"   Request ID: {req_id_2}")
        except:
            req_id_2 = "unknown"
    else:
        print(f"   Error: {stderr2}")
        return

    print()

    # Check if responses are identical
    if stdout1 == stdout2:
        print("✅ SUCCESS: Both responses are identical!")
        print("   This confirms idempotency is working correctly.")
    else:
        print("❌ FAILURE: Responses are different!")
        print("   Idempotency is not working as expected.")
        print(f"   First:  {stdout1}")
        print(f"   Second: {stdout2}")


if __name__ == "__main__":
    test_idempotency()
