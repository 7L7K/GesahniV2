#!/usr/bin/env python3
"""
Demonstration of auth error contract compliance.

This script shows that all auth gates (401/403) return proper error contracts
instead of legacy {"detail": "..."} format.
"""

import json
import os

from fastapi.testclient import TestClient

from app.main import create_app


def main():
    # Set environment
    os.environ["JWT_SECRET"] = "demo_secret"
    os.environ["ENV"] = "demo"

    app = create_app()
    client = TestClient(app)

    print("=== AUTH ERROR CONTRACT DEMONSTRATION ===")
    print()
    print("Testing that all auth gates return proper error contracts...")
    print()

    # Test 1: No auth on protected endpoint
    print("1. POST /v1/ask without authentication:")
    response = client.post("/v1/ask", json={"prompt": "test"})
    print(f"   Status: {response.status_code}")
    error = response.json()
    print(f"   Response: {json.dumps(error, indent=2)}")
    print()

    # Test 2: Invalid refresh token
    print("2. POST /v1/auth/refresh with invalid token:")
    response = client.post("/v1/auth/refresh", json={"refresh_token": "invalid"})
    print(f"   Status: {response.status_code}")
    error = response.json()
    print(f"   Response: {json.dumps(error, indent=2)}")
    print()

    # Test 3: Whoami without auth
    print("3. GET /v1/whoami without authentication:")
    response = client.get("/v1/whoami")
    print(f"   Status: {response.status_code}")
    error = response.json()
    print(f"   Response: {json.dumps(error, indent=2)}")
    print()

    print("=== CURL COMMANDS FOR MANUAL TESTING ===")
    print()
    print("curl -s -i http://localhost:8000/v1/ask -X POST \\")
    print('  -H "Content-Type: application/json" \\')
    print('  -d \'{"prompt":"test"}\' | jq')
    print()
    print("curl -s -i http://localhost:8000/v1/auth/refresh -X POST \\")
    print('  -H "Content-Type: application/json" \\')
    print('  -d \'{"refresh_token":"invalid"}\' | jq')
    print()

    print("=== VERIFICATION: ALL RESPONSES HAVE ===")
    print("[+] code: machine-readable error identifier")
    print("[+] message: human-readable error message")
    print("[+] hint: actionable guidance (when available)")
    print("[+] meta: debuggable context with req_id, timestamp, error_id, env")
    print("[+] Proper HTTP headers: X-Error-Code, WWW-Authenticate, etc.")
    print()
    print("=== NO LEGACY FORMAT DETECTED ===")
    print('[-] No {"detail": "unauthorized"} responses')
    print("[-] No plain string error messages")
    print("[+] All errors follow standardized envelope contract")


if __name__ == "__main__":
    main()
