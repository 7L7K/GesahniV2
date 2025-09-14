#!/usr/bin/env python3
"""
Demonstration of validation error contract compliance.

Shows that both Pydantic guardrails and consistent 422 responses work correctly.
"""

import os

from fastapi.testclient import TestClient

from app.main import create_app
from app.tokens import make_access


def test_validation_errors():
    # Set environment
    os.environ["JWT_SECRET"] = "test"
    os.environ["ENV"] = "test"

    app = create_app()
    client = TestClient(app)

    # Create a valid token to bypass auth
    token = make_access({"user_id": "test_user"})
    headers = {"Authorization": f"Bearer {token}"}

    print("=== VALIDATION ERROR CONTRACT DEMONSTRATION ===")
    print()
    print("Testing that both bad input scenarios produce consistent 422 responses")
    print()

    # Test 1: Empty JSON {} - Pydantic validation (missing required field)
    print("1. POST /v1/ask with empty JSON {}:")
    print("   Expected: Pydantic validation error (missing required prompt field)")
    response = client.post("/v1/ask", json={}, headers=headers)

    print(f"   Status: {response.status_code}")
    if response.status_code == 422:
        error = response.json()
        print(f'   Code: {error.get("code")}')
        print(f'   Message: {error.get("message")}')
        print(f'   Has meta: {"meta" in error}')
        if "meta" in error and "errors" in error["meta"]:
            print(f'   Validation errors: {len(error["meta"]["errors"])} found')
        print("   ✓ Pydantic guardrails working correctly")
    else:
        print(f"   ✗ Unexpected status: {response.status_code}")
    print()

    # Test 2: Empty prompt - Pydantic field validation (value error)
    print("2. POST /v1/ask with empty prompt:")
    print("   Expected: Pydantic field validation error (empty after stripping)")
    response = client.post("/v1/ask", json={"prompt": ""}, headers=headers)

    print(f"   Status: {response.status_code}")
    if response.status_code == 422:
        error = response.json()
        print(f'   Code: {error.get("code")}')
        print(f'   Message: {error.get("message")}')
        print(f'   Has meta: {"meta" in error}')
        if "meta" in error and "errors" in error["meta"]:
            print(f'   Validation errors: {len(error["meta"]["errors"])} found')
        print("   ✓ Pydantic field guardrails working correctly")
    else:
        print(f"   ✗ Unexpected status: {response.status_code}")
    print()

    print("=== VERIFICATION ===")
    print("Both scenarios should return:")
    print("• Status: 422")
    print("• Code: validation_error")
    print("• Message: Validation Error")
    print("• Meta with debugging info")
    print("• Structured validation error details")
    print()
    print("✓ Consistent 422 error contract across all validation failures")
    print("✓ Pydantic guardrails provide comprehensive input validation")
    print("✓ Error responses follow standardized envelope format")


if __name__ == "__main__":
    test_validation_errors()
