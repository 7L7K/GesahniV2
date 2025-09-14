#!/usr/bin/env python3
"""
Dump all mounted routes from the FastAPI app at runtime.
"""

import json
import os
import sys

# Add the project root to sys.path
sys.path.insert(0, os.path.dirname(__file__))

# Import and create the app properly
from app.main import create_app

# Create the app with all routers properly mounted
app = create_app()


def dump_routes():
    """Dump all routes from the FastAPI app to JSON and text formats."""

    routes_data = []

    for route in app.routes:
        # Skip mounted apps (StaticFiles, etc.)
        if hasattr(route, "methods"):
            methods = list(route.methods)
            path = route.path
            name = getattr(route, "name", None) or ""

            # Get the endpoint function name
            endpoint = getattr(route, "endpoint", None)
            endpoint_name = getattr(endpoint, "__name__", "") if endpoint else ""

            routes_data.append(
                {
                    "path": path,
                    "methods": methods,
                    "name": name,
                    "endpoint": endpoint_name,
                }
            )

    # Sort by path
    routes_data.sort(key=lambda x: x["path"])

    # Write JSON
    with open("artifacts/test_baseline/routes.json", "w") as f:
        json.dump(routes_data, f, indent=2)

    # Write text format
    with open("artifacts/test_baseline/routes.txt", "w") as f:
        for route in routes_data:
            methods_str = ",".join(route["methods"])
            f.write(f"{methods_str},{route['path']} -> {route['endpoint']}\n")

        f.write(f"\nTotal routes: {len(routes_data)}\n")

    print(f"Dumped {len(routes_data)} routes to artifacts/test_baseline/")


if __name__ == "__main__":
    dump_routes()
