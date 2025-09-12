#!/usr/bin/env python3
"""
Export OpenAPI spec from the FastAPI app at runtime.
"""

import json
import os
import sys

# Add the project root to sys.path
sys.path.insert(0, os.path.dirname(__file__))

# Import the app from main.py
from app.main import app


def export_openapi():
    """Export OpenAPI spec from the FastAPI app."""

    # Get the OpenAPI schema
    schema = app.openapi()

    # Write to file
    with open('artifacts/test_baseline/openapi.json', 'w') as f:
        json.dump(schema, f, indent=2)

    print(f"Exported OpenAPI spec with {len(schema.get('paths', {}))} paths to artifacts/test_baseline/openapi.json")

if __name__ == '__main__':
    export_openapi()
