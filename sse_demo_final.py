#!/usr/bin/env python3
"""
Final SSE streaming performance demonstration.

Uses curl with head -5 to verify data events appear within 2 seconds.
"""

import os
import subprocess
import sys
import time


def get_jwt_token():
    """Get JWT token using the correct secret from .env"""
    with open(".env") as f:
        for line in f:
            if line.startswith("JWT_SECRET="):
                secret = line.split("=", 1)[1].strip()
                break
        else:
            raise ValueError("JWT_SECRET not found in .env")

    # Generate token
    os.environ["JWT_SECRET"] = secret
    from app.tokens import make_access

    return make_access({"user_id": "test_user"})


def test_sse_streaming():
    """Test SSE streaming with curl + head -5"""

    print("=== SSE STREAMING PERFORMANCE TEST ===")
    print()
    print("Testing /v1/ask/stream with curl + head -5")
    print("Verifying data events appear within 2 seconds")
    print()

    # Get token
    token = get_jwt_token()
    print("✅ Generated JWT token")

    # Test command
    cmd = [
        "curl",
        "-s",
        "-N",
        "-H",
        f"Authorization: Bearer {token}",
        "-H",
        "Content-Type: application/json",
        "-H",
        "Accept: text/event-stream",
        "-d",
        '{"prompt": "What is the capital of France?"}',
        "http://localhost:8000/v1/ask/stream",
    ]

    print("Running: curl -s -N -H 'Authorization: Bearer [token]' ... | head -5")

    # Start timing
    start_time = time.time()

    # Run curl | head -5
    curl_proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    head_proc = subprocess.Popen(
        ["head", "-5"],
        stdin=curl_proc.stdout,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    # Get output
    output, error = head_proc.communicate(timeout=10)

    # Calculate elapsed time
    elapsed = time.time() - start_time

    print()
    print("=== CAPTURED OUTPUT ===")
    print("-" * 50)
    print(output.strip())
    print("-" * 50)
    print()

    # Analyze results
    lines = output.strip().split("\n")
    data_lines = [line for line in lines if line.startswith("data: ")]

    print("Analysis:")
    print(f"  Total lines: {len(lines)}")
    print(f"  Data events: {len(data_lines)}")
    print(f"  Time elapsed: {elapsed:.3f}s")
    print()

    # Check requirements
    if elapsed < 2.0 and len(data_lines) > 0:
        print("✅ SUCCESS: SSE streaming works correctly!")
        print(f"   ✓ Data events appeared in {elapsed:.3f}s (< 2.0s)")
        print(f"   ✓ Found {len(data_lines)} data events")
        print()
        print("🎉 Scriptable proof achieved!")
        print("   curl + head -5 shows data events in < 2s")
        return True
    else:
        print("❌ FAILURE: Requirements not met")
        if elapsed >= 2.0:
            print(f"   ✗ Time exceeded: {elapsed:.3f}s >= 2.0s")
        if len(data_lines) == 0:
            print("   ✗ No data events found")
            print("   → Check if LLM backend (OpenAI/Ollama) is available")
        return False


if __name__ == "__main__":
    success = test_sse_streaming()
    sys.exit(0 if success else 1)
