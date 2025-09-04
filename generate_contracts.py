#!/usr/bin/env python3
"""
Generate OpenAPI contract snapshots for different environments.

This script creates frozen snapshots of the OpenAPI schema that serve as contracts
to ensure API changes are intentional and tracked.

Usage:
    python generate_contracts.py

The script will generate/update:
- contracts/openapi.ci.json (CI mode, minimal surface)
- contracts/openapi.dev.min.json (Dev mode, minimal surface)
- contracts/openapi.dev.spotify.json (Dev mode with Spotify enabled)
- contracts/openapi.prod.min.json (Prod mode, minimal surface - if available)
"""

import json
import os
import sys
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import create_app


def get_schema(client):
    """Get OpenAPI schema from client, handling 404 gracefully."""
    try:
        r = client.get("/openapi.json")
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"⚠️  Failed to get schema: {e}")
        return None


def save_schema(schema, path, description):
    """Save schema to JSON file."""
    if schema is None:
        print(f"⚠️  Skipping {description} - schema not available")
        return

    with open(path, "w", encoding="utf-8") as f:
        json.dump(schema, f, indent=2, sort_keys=True)
    print(f"✅ Saved {description} to {path}")


def generate_ci_contract():
    """Generate CI environment contract."""
    print("\n🔧 Generating CI contract...")

    # Set CI environment
    os.environ["CI"] = "1"
    # Clear optional integrations
    os.environ.pop("SPOTIFY_ENABLED", None)
    os.environ.pop("APPLE_OAUTH_ENABLED", None)
    os.environ.pop("DEVICE_AUTH_ENABLED", None)

    app = create_app()
    client = TestClient(app)
    schema = get_schema(client)

    contracts_dir = Path(__file__).parent / "contracts"
    contracts_dir.mkdir(exist_ok=True)

    save_schema(schema, contracts_dir / "openapi.ci.json", "CI contract")

    # Clean up env
    os.environ.pop("CI", None)


def generate_dev_min_contract():
    """Generate dev minimal environment contract."""
    print("\n🔧 Generating dev minimal contract...")

    # Clear CI and optional integrations
    os.environ.pop("CI", None)
    os.environ.pop("SPOTIFY_ENABLED", None)
    os.environ.pop("APPLE_OAUTH_ENABLED", None)
    os.environ.pop("DEVICE_AUTH_ENABLED", None)

    app = create_app()
    client = TestClient(app)
    schema = get_schema(client)

    contracts_dir = Path(__file__).parent / "contracts"
    save_schema(schema, contracts_dir / "openapi.dev.min.json", "dev minimal contract")


def generate_dev_spotify_contract():
    """Generate dev with Spotify enabled contract."""
    print("\n🔧 Generating dev + Spotify contract...")

    # Clear CI, enable Spotify
    os.environ.pop("CI", None)
    os.environ["SPOTIFY_ENABLED"] = "1"
    os.environ.pop("APPLE_OAUTH_ENABLED", None)
    os.environ.pop("DEVICE_AUTH_ENABLED", None)

    app = create_app()
    client = TestClient(app)
    schema = get_schema(client)

    contracts_dir = Path(__file__).parent / "contracts"
    save_schema(schema, contracts_dir / "openapi.dev.spotify.json", "dev + Spotify contract")

    # Clean up env
    os.environ.pop("SPOTIFY_ENABLED", None)


def generate_prod_contract():
    """Generate prod environment contract."""
    print("\n🔧 Generating prod contract...")

    # Clear CI and optional integrations, set prod
    os.environ.pop("CI", None)
    os.environ.pop("SPOTIFY_ENABLED", None)
    os.environ.pop("APPLE_OAUTH_ENABLED", None)
    os.environ.pop("DEVICE_AUTH_ENABLED", None)
    os.environ["ENV"] = "prod"

    app = create_app()
    client = TestClient(app)
    schema = get_schema(client)

    contracts_dir = Path(__file__).parent / "contracts"
    save_schema(schema, contracts_dir / "openapi.prod.min.json", "prod minimal contract")

    # Clean up env
    os.environ.pop("ENV", None)


def main():
    """Main entry point."""
    print("🚀 Generating OpenAPI contract snapshots...")

    # Backup original environment
    original_env = dict(os.environ)

    try:
        generate_ci_contract()
        generate_dev_min_contract()
        generate_dev_spotify_contract()
        generate_prod_contract()

        print("\n✅ All contract snapshots generated successfully!")
        print("\n📝 Next steps:")
        print("1. Review the generated contract files in contracts/")
        print("2. Run contract tests: python -m pytest tests/contract/ -v")
        print("3. If tests pass, commit the updated contracts with your changes")

    except Exception as e:
        print(f"❌ Error generating contracts: {e}")
        sys.exit(1)

    finally:
        # Restore original environment
        os.environ.clear()
        os.environ.update(original_env)


if __name__ == "__main__":
    main()
