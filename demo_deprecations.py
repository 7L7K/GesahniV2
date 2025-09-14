#!/usr/bin/env python3
"""
Demonstration of API deprecation functionality.
Shows deprecated routes and their OpenAPI documentation.
"""

from fastapi.testclient import TestClient

from app.main import create_app


def demo_deprecations():
    """Demonstrate API deprecation functionality."""

    print("🔄 API Deprecation Demonstration")
    print("=" * 50)

    app = create_app()
    client = TestClient(app)

    # 1. Check OpenAPI spec for deprecated routes
    print("\n1. OpenAPI Spec - Deprecated Routes:")
    print("-" * 40)

    response = client.get("/openapi.json")
    spec = response.json()
    paths = spec["paths"]

    deprecated_found = []
    for path, path_spec in paths.items():
        for method, method_spec in path_spec.items():
            if isinstance(method_spec, dict) and method_spec.get("deprecated"):
                deprecated_found.append(f"{method.upper()} {path}")
                print(f"  ⚠️  {method.upper()} {path}")

    if not deprecated_found:
        print("  ℹ️  No deprecated routes found in OpenAPI spec")
    else:
        print(f"\n  📊 Found {len(deprecated_found)} deprecated routes")

    # 2. Test deprecated route functionality
    print("\n2. Testing Deprecated Route Functionality:")
    print("-" * 40)

    test_routes = [
        ("/whoami", "User info compatibility route"),
        ("/spotify/status", "Spotify status compatibility route"),
        ("/google/status", "Google status compatibility route"),
    ]

    for route, description in test_routes:
        try:
            response = client.get(route)
            status_emoji = "✅" if response.status_code < 400 else "⚠️"
            print(f"  {status_emoji} {route} -> {response.status_code} ({description})")
        except Exception as e:
            print(f"  ❌ {route} -> Error: {e}")

    # 3. Show deprecation documentation
    print("\n3. Deprecation Documentation:")
    print("-" * 40)

    try:
        with open("DEPRECATIONS.md") as f:
            content = f.read()

        # Count deprecated endpoints
        lines = content.split("\n")
        table_lines = [
            line for line in lines if "|" in line and ("GET" in line or "POST" in line)
        ]
        print(
            f"  📄 DEPRECATIONS.md exists with {len(table_lines)} documented deprecated endpoints"
        )

        # Show a few examples
        if table_lines:
            print("\n  📋 Examples from documentation:")
            for line in table_lines[:3]:  # Show first 3 examples
                if "GET" in line or "POST" in line:
                    parts = [part.strip() for part in line.split("|") if part.strip()]
                    if len(parts) >= 2:
                        print(f"    • {parts[1]}")

    except FileNotFoundError:
        print("  ❌ DEPRECATIONS.md file not found")

    print(f"\n{'=' * 50}")
    print("🎯 Deprecation Demo Complete!")
    print("\nKey Points:")
    print("- Deprecated routes are marked with 'deprecated: true' in OpenAPI")
    print("- Routes remain functional during deprecation grace period")
    print("- DEPRECATIONS.md documents removal timelines and migration paths")
    print("- Clients should migrate to versioned API endpoints (/v1/*)")


if __name__ == "__main__":
    demo_deprecations()
