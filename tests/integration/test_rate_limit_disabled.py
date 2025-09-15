#!/usr/bin/env python3
"""
Test script to verify rate limiting is disabled in test environment
"""

import os
import sys

# Set test environment
os.environ["PYTEST_RUNNING"] = "1"
os.environ["TEST_MODE"] = "1"

sys.path.insert(0, ".")

# Import conftest to set up test environment
import app.env_utils as env_utils

env_utils.load_env()

# Import app
from fastapi.testclient import TestClient

from app.main import app


def test_rate_limit_disabled():
    """Test that rate limiting is disabled in test environment."""
    client = TestClient(app)

    # Make a few requests - should not be rate limited
    # Note: We use a smaller number since health checks are slow (~0.7s each)
    # and we want this test to complete quickly even with --timeout=30
    for i in range(10):
        response = client.get("/health")
        print(f"Request {i+1}: Status {response.status_code}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        if response.status_code == 429:
            print("ERROR: Rate limiting is still active!")
            assert False, "Rate limiting should be disabled in test environment"

    print("SUCCESS: Rate limiting is disabled!")
    assert True


if __name__ == "__main__":
    success = test_rate_limit_disabled()
    sys.exit(0 if success else 1)
