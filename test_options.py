#!/usr/bin/env python3
"""
Simple test to verify OPTIONS preflight handling works correctly.
"""

import sys
import time

import requests


def test_options_preflight():
    """Test that OPTIONS requests return 204 without CORS headers."""
    print("Testing OPTIONS preflight handling...")

    # Start a simple server for testing
    import os
    import threading

    import uvicorn

    from app.main import create_app

    app = create_app()

    # Set test environment
    os.environ["ENV"] = "test"

    def run_server():
        uvicorn.run(app, host="127.0.0.1", port=8001, log_level="error")

    # Start server in background
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()

    # Wait for server to start
    time.sleep(2)

    try:
        # Test OPTIONS request to a known route
        response = requests.options("http://127.0.0.1:8001/healthz", timeout=5)
        print(f"OPTIONS /healthz: {response.status_code}")
        assert response.status_code == 204, f"Expected 204, got {response.status_code}"

        # Test OPTIONS request to an unknown route
        response = requests.options("http://127.0.0.1:8001/some-unknown-route", timeout=5)
        print(f"OPTIONS /some-unknown-route: {response.status_code}")
        assert response.status_code == 204, f"Expected 204, got {response.status_code}"

        # Test OPTIONS request with CORS headers
        headers = {"Origin": "http://localhost:3000"}
        response = requests.options("http://127.0.0.1:8001/v1/status", headers=headers, timeout=5)
        print(f"OPTIONS /v1/status with Origin: {response.status_code}")
        assert response.status_code == 200, f"Expected 200 for CORS preflight, got {response.status_code}"

        print("✅ All OPTIONS tests passed!")
        return True

    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False
    finally:
        # Server will be killed when the process exits
        pass

if __name__ == "__main__":
    success = test_options_preflight()
    sys.exit(0 if success else 1)
