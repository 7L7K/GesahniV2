#!/usr/bin/env python3
import os
import sys

# Set test environment
os.environ["TEST_MODE"] = "1"
os.environ["PYTEST_RUNNING"] = "1"

# Add current directory to Python path
sys.path.insert(0, os.path.dirname(__file__))

# Import and run uvicorn
import uvicorn

if __name__ == "__main__":
    # Only run the dev server when executed directly. Importing this module
    # during pytest collection should not start the server.
    uvicorn.run(
        "app.main:app", host="127.0.0.1", port=8000, reload=False, log_level="warning"
    )
