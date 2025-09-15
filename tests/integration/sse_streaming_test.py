#!/usr/bin/env python3
"""
Scriptable SSE streaming performance test.

Verifies that data events appear within 2 seconds using head -5 on curl stream.
"""

import os
import subprocess
import sys
import time

from fastapi.testclient import TestClient

from app.main import create_app
from app.tokens import make_access


def test_sse_streaming():
    """Test SSE streaming performance with scriptable verification."""

    # Set environment
    os.environ["JWT_SECRET"] = "test"
    os.environ["ENV"] = "dev"  # Set to dev for testing
    os.environ["DEV_STREAM_FAKE"] = "1"  # Enable fake streaming

    app = create_app()
    client = TestClient(app)

    # Create a test token
    token = make_access({"user_id": "test_user"})

    print("=== SSE STREAMING PERFORMANCE TEST ===")
    print()
    print("Testing /v1/ask/stream endpoint with head -5")
    print("Verifying data events appear within 2 seconds")
    print()

    # First, get CSRF token
    print("1. Getting CSRF token...")
    csrf_response = client.get("/v1/csrf")
    if csrf_response.status_code != 200:
        print(f"❌ Failed to get CSRF token: {csrf_response.status_code}")
        return False

    csrf_token = csrf_response.json().get("csrf_token")
    if not csrf_token:
        print("❌ No CSRF token in response")
        return False

    print(f"✅ Got CSRF token: {csrf_token[:16]}...")
    print()

    # Test with TestClient to make sure the endpoint works
    print("2. Testing endpoint availability...")
    headers = {"Authorization": f"Bearer {token}", "X-CSRF-Token": csrf_token}

    # Test basic connectivity first
    response = client.post("/v1/ask/stream", json={"prompt": "Hello"}, headers=headers)

    if response.status_code != 200:
        print(f"❌ Endpoint not available: {response.status_code}")
        print(f"Response: {response.text[:200]}")
        return False

    print("✅ Endpoint available")
    print()

    # Now test with curl and timing
    print("3. Testing streaming performance with curl...")

    # Prepare curl command with CSRF token
    curl_cmd = [
        "curl",
        "-s",
        "-N",
        "-H",
        f"Authorization: Bearer {token}",
        "-H",
        f"X-CSRF-Token: {csrf_token}",
        "-H",
        "Content-Type: application/json",
        "-H",
        "Accept: text/event-stream",
        "-d",
        '{"prompt": "What is the capital of France?"}',
        "http://localhost:8000/v1/ask/stream",
    ]

    # Add head -5 to capture first 5 lines
    head_cmd = ["head", "-5"]

    try:
        # Start timing
        start_time = time.time()

        # Run curl | head -5
        curl_proc = subprocess.Popen(
            curl_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        head_proc = subprocess.Popen(
            head_cmd,
            stdin=curl_proc.stdout,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        # Get output
        output, error = head_proc.communicate(timeout=10)

        # Calculate elapsed time
        elapsed = time.time() - start_time

        print("Captured output:")
        print("-" * 40)
        print(output.strip())
        print("-" * 40)
        print()

        # Check for data events
        lines = output.strip().split("\n")
        data_lines = [line for line in lines if line.startswith("data: ")]

        print("Results:")
        print(f"  Total lines captured: {len(lines)}")
        print(f"  Data lines found: {len(data_lines)}")
        print(f"  Time elapsed: {elapsed:.3f}s")
        print()

        # Verify performance
        if elapsed < 2.0 and len(data_lines) > 0:
            print("✅ SUCCESS: Data events appeared within 2 seconds!")
            print(f"   Found {len(data_lines)} data events in {elapsed:.3f}s")
            return True
        else:
            print("❌ FAILURE: Performance requirements not met")
            if elapsed >= 2.0:
                print(f"   Time exceeded: {elapsed:.3f}s > 2.0s")
            if len(data_lines) == 0:
                print("   No data events found in captured output")
            return False

    except subprocess.TimeoutExpired:
        print("❌ FAILURE: Test timed out")
        return False
    except Exception as e:
        print(f"❌ FAILURE: Error running test: {e}")
        return False


def print_bash_test():
    """Print bash one-liner for testing SSE streaming."""
    print("=== BASH ONE-LINER FOR SSE TESTING ===")
    print()
    print("# Set environment and test streaming endpoint")
    print("export ENV=dev DEV_STREAM_FAKE=1 DEV_AUTH=1 && \\")
    print(
        "TOKEN=$(curl -s -X POST -H 'Content-Type: application/json' -d '{\"username\": \"test_user\"}' http://localhost:8000/v1/auth/dev/login | jq -r '.access_token') && \\"
    )
    print(
        "CSRF_TOKEN=$(curl -s -H \"Authorization: Bearer $TOKEN\" http://localhost:8000/v1/csrf | jq -r '.csrf_token') && \\"
    )
    print("echo 'Starting streaming test...' && \\")
    print("time curl -N -X POST \\")
    print('  -H "Authorization: Bearer $TOKEN" \\')
    print('  -H "X-CSRF-Token: $CSRF_TOKEN" \\')
    print("  -H 'Content-Type: application/json' \\")
    print("  -H 'Accept: text/event-stream' \\")
    print('  -d \'{"prompt": "Hello world"}\' \\')
    print("  http://localhost:8000/v1/ask/stream | head -5")
    print()
    print("# Expected output should show data: lines within <2 seconds")
    print()


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--bash":
        print_bash_test()
    else:
        success = test_sse_streaming()
        sys.exit(0 if success else 1)
