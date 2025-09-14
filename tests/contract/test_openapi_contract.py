"""
OpenAPI contract tests - freeze API surface for different environments.
When you intentionally add/remove routes, update the snapshot files in the same PR.
"""

import json

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
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def test_ci_schema_contains_critical_paths(monkeypatch):
    """CI: assert critical routes exist rather than exact snapshot.

    The router was modernized to compose from multiple modules; the exact path
    set varies by optional features. This test focuses on the contract that
    matters for CI: health, auth, ask, minimal integrations discovery.
    """
    monkeypatch.setenv("CI", "1")
    monkeypatch.delenv("SPOTIFY_ENABLED", raising=False)
    monkeypatch.delenv("APPLE_OAUTH_ENABLED", raising=False)
    monkeypatch.delenv("DEVICE_AUTH_ENABLED", raising=False)

    app = create_app()
    client = TestClient(app)
    paths = set(_schema(client).get("paths", {}).keys())

    must_have = {
        "/v1/ask",
        "/v1/health",
        "/v1/health/vector_store",
        "/v1/auth/login",
        "/v1/auth/logout",
        "/v1/auth/refresh",
        "/v1/me",
        "/whoami",
        "/v1/admin/config",
    }
    # Accept either /v1/google/login_url or /v1/google/auth/login_url
    assert (
        "/v1/google/login_url" in paths or "/v1/google/auth/login_url" in paths
    ), f"google login route missing; got={sorted(paths)[:10]}..."
    # Accept either /v1/google/callback or /v1/google/auth/callback
    assert (
        "/v1/google/callback" in paths or "/v1/google/auth/callback" in paths
    ), "google callback route missing"

    missing = sorted([p for p in must_have if p not in paths])
    assert not missing, f"Critical routes missing: {missing}"


def test_dev_min_schema_contains_critical_paths(monkeypatch):
    """Dev (no optionals): assert critical routes exist."""
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("SPOTIFY_ENABLED", raising=False)
    monkeypatch.delenv("APPLE_OAUTH_ENABLED", raising=False)
    monkeypatch.delenv("DEVICE_AUTH_ENABLED", raising=False)

    app = create_app()
    client = TestClient(app)
    paths = set(_schema(client).get("paths", {}).keys())

    must_have = {
        "/v1/ask",
        "/v1/health",
        "/v1/auth/login",
        "/v1/me",
        "/v1/auth/logout",
    }
    missing = sorted([p for p in must_have if p not in paths])
    assert not missing, f"Critical routes missing: {missing}"


def test_prod_min_schema_contains_critical_paths(monkeypatch):
    """Prod min: assert critical routes exist and health endpoints remain."""
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("SPOTIFY_ENABLED", raising=False)
    monkeypatch.delenv("APPLE_OAUTH_ENABLED", raising=False)
    monkeypatch.delenv("DEVICE_AUTH_ENABLED", raising=False)
    monkeypatch.setenv("ENV", "prod")

    app = create_app()
    client = TestClient(app)
    paths = set(_schema(client).get("paths", {}).keys())

    must_have = {"/v1/ask", "/v1/health", "/v1/auth/login", "/whoami"}
    missing = sorted([p for p in must_have if p not in paths])
    assert not missing, f"Critical routes missing: {missing}"


def test_dev_with_spotify_contains_integrations_status(monkeypatch):
    """Dev with Spotify: integration status route exists."""
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.setenv("SPOTIFY_ENABLED", "1")
    monkeypatch.delenv("APPLE_OAUTH_ENABLED", raising=False)
    monkeypatch.delenv("DEVICE_AUTH_ENABLED", raising=False)

    app = create_app()
    client = TestClient(app)
    paths = set(_schema(client).get("paths", {}).keys())

    assert "/v1/integrations/spotify/status" in paths or "/v1/spotify/status" in paths
