"""
OpenAPI contract tests - freeze API surface for different environments.
When you intentionally add/remove routes, update the snapshot files in the same PR.
"""
import json
import os
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import create_app


def _schema(client):
    """Get OpenAPI schema from client."""
    r = client.get("/openapi.json")
    r.raise_for_status()
    return r.json()


def _keys(d):
    """Get sorted keys from dict for stable comparison."""
    return sorted((d or {}).keys())


def _load(path):
    """Load JSON from file."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def test_ci_schema_paths_match_snapshot(monkeypatch):
    """Test that CI environment schema matches snapshot."""
    monkeypatch.setenv("CI", "1")
    # Clear any optional integrations
    monkeypatch.delenv("SPOTIFY_ENABLED", raising=False)
    monkeypatch.delenv("APPLE_OAUTH_ENABLED", raising=False)
    monkeypatch.delenv("DEVICE_AUTH_ENABLED", raising=False)

    app = create_app()
    client = TestClient(app)
    cur = _schema(client)

    snapshot_path = Path(__file__).parent.parent.parent / "contracts" / "openapi.ci.json"
    snap = _load(snapshot_path)

    assert _keys(cur["paths"]) == _keys(snap["paths"]), \
        f"CI schema paths don't match snapshot. Expected: {_keys(snap['paths'])}, Got: {_keys(cur['paths'])}"


def test_dev_min_schema_paths_match_snapshot(monkeypatch):
    """Test that dev environment (no optionals) schema matches snapshot."""
    # Clear CI and optional integrations
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("SPOTIFY_ENABLED", raising=False)
    monkeypatch.delenv("APPLE_OAUTH_ENABLED", raising=False)
    monkeypatch.delenv("DEVICE_AUTH_ENABLED", raising=False)

    app = create_app()
    client = TestClient(app)
    cur = _schema(client)

    snapshot_path = Path(__file__).parent.parent.parent / "contracts" / "openapi.dev.min.json"
    snap = _load(snapshot_path)

    assert _keys(cur["paths"]) == _keys(snap["paths"]), \
        f"Dev minimum schema paths don't match snapshot. Expected: {_keys(snap['paths'])}, Got: {_keys(cur['paths'])}"


def test_prod_min_schema_paths_match_snapshot(monkeypatch):
    """Test that prod environment schema matches snapshot."""
    # Clear CI and optional integrations
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("SPOTIFY_ENABLED", raising=False)
    monkeypatch.delenv("APPLE_OAUTH_ENABLED", raising=False)
    monkeypatch.delenv("DEVICE_AUTH_ENABLED", raising=False)
    # Set prod environment
    monkeypatch.setenv("ENV", "prod")

    app = create_app()
    client = TestClient(app)
    cur = _schema(client)

    snapshot_path = Path(__file__).parent.parent.parent / "contracts" / "openapi.prod.min.json"
    snap = _load(snapshot_path)

    assert _keys(cur["paths"]) == _keys(snap["paths"]), \
        f"Prod minimum schema paths don't match snapshot. Expected: {_keys(snap['paths'])}, Got: {_keys(cur['paths'])}"


def test_dev_with_spotify_schema_paths_match_snapshot(monkeypatch):
    """Test that dev environment with Spotify enabled has expected additional routes."""
    # Clear CI, enable Spotify
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.setenv("SPOTIFY_ENABLED", "1")
    monkeypatch.delenv("APPLE_OAUTH_ENABLED", raising=False)
    monkeypatch.delenv("DEVICE_AUTH_ENABLED", raising=False)

    app = create_app()
    client = TestClient(app)
    cur = _schema(client)

    snapshot_path = Path(__file__).parent.parent.parent / "contracts" / "openapi.dev.spotify.json"
    snap = _load(snapshot_path)

    assert _keys(cur["paths"]) == _keys(snap["paths"]), \
        f"Dev with Spotify schema paths don't match snapshot. Expected: {_keys(snap['paths'])}, Got: {_keys(cur['paths'])}"
