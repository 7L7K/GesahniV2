"""
Phase 6.5.c: Granular RBAC Scope Tests
Tests that admin endpoints properly enforce granular scopes
"""

import os
import time

import jwt
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    """Test client fixture"""
    return TestClient(app)


@pytest.fixture(autouse=True)
def setup_jwt_secret():
    """Ensure JWT_SECRET is set for all tests"""
    if "JWT_SECRET" not in os.environ:
        os.environ["JWT_SECRET"] = "test-secret-key-for-jwt-tokens-in-tests"
    # Enforce strict expired-token behavior in tests
    os.environ.setdefault("JWT_CLOCK_SKEW_S", "0")


def _tok(scopes, user_id="test-user-123"):
    """Generate JWT token with specified scopes"""
    key = os.environ["JWT_SECRET"]  # Use the same secret as the app
    now = int(time.time())
    payload = {
        "sub": user_id,
        "iat": now,
        "exp": now + 300,  # Longer TTL for tests
        "scopes": scopes
    }
    return jwt.encode(payload, key, algorithm="HS256")


def test_admin_read_requires_read_or_admin_scope(client):
    """Test that admin read endpoints require admin:read or admin scope"""
    # Test with admin:read scope - should succeed
    token_read = _tok(["admin:read"])
    response = client.get("/v1/admin/config", headers={"Authorization": f"Bearer {token_read}"})
    assert response.status_code == 200

    # Test with admin scope - should succeed
    token_admin = _tok(["admin"])
    response = client.get("/v1/admin/config", headers={"Authorization": f"Bearer {token_admin}"})
    assert response.status_code == 200

    # Test with insufficient scope - should fail
    token_insufficient = _tok(["user:profile"])
    response = client.get("/v1/admin/config", headers={"Authorization": f"Bearer {token_insufficient}"})
    assert response.status_code == 403

    # Test without token - should fail
    response = client.get("/v1/admin/config")
    assert response.status_code == 401


def test_admin_write_requires_write_or_admin_scope(client):
    """Test that admin write endpoints require admin:write or admin scope"""
    test_data = {"test": "data"}

    # Test with admin:write scope - should succeed
    token_write = _tok(["admin:write"])
    response = client.post("/v1/admin/config/test", json=test_data, headers={"Authorization": f"Bearer {token_write}"})
    assert response.status_code == 200

    # Test with admin scope - should succeed
    token_admin = _tok(["admin"])
    response = client.post("/v1/admin/config/test", json=test_data, headers={"Authorization": f"Bearer {token_admin}"})
    assert response.status_code == 200

    # Test with admin:read only - should fail
    token_read = _tok(["admin:read"])
    response = client.post("/v1/admin/config/test", json=test_data, headers={"Authorization": f"Bearer {token_read}"})
    assert response.status_code == 403

    # Test without token - should fail
    response = client.post("/v1/admin/config/test", json=test_data)
    assert response.status_code == 401


def test_admin_metrics_endpoint_scope(client):
    """Test that /v1/admin/metrics requires admin:read or admin scope"""
    # Test with admin:read scope - should succeed
    token_read = _tok(["admin:read"])
    response = client.get("/v1/admin/metrics", headers={"Authorization": f"Bearer {token_read}"})
    assert response.status_code == 200

    # Test with admin scope - should succeed
    token_admin = _tok(["admin"])
    response = client.get("/v1/admin/metrics", headers={"Authorization": f"Bearer {token_admin}"})
    assert response.status_code == 200

    # Test with insufficient scope - should fail
    token_insufficient = _tok(["user:profile"])
    response = client.get("/v1/admin/metrics", headers={"Authorization": f"Bearer {token_insufficient}"})
    assert response.status_code == 403


def test_admin_system_status_endpoint_scope(client):
    """Test that system status endpoints require admin:read or admin scope"""
    # Test with admin:read scope - should succeed
    token_read = _tok(["admin:read"])
    response = client.get("/v1/admin/system/status", headers={"Authorization": f"Bearer {token_read}"})
    assert response.status_code == 200

    # Test with admin scope - should succeed
    token_admin = _tok(["admin"])
    response = client.get("/v1/admin/system/status", headers={"Authorization": f"Bearer {token_admin}"})
    assert response.status_code == 200

    # Test with insufficient scope - should fail
    token_insufficient = _tok(["user:profile"])
    response = client.get("/v1/admin/system/status", headers={"Authorization": f"Bearer {token_insufficient}"})
    assert response.status_code == 403


def test_admin_flags_endpoint_scope(client):
    """Test that flags endpoint requires admin:read or admin scope"""
    # Test with admin:read scope - should succeed
    token_read = _tok(["admin:read"])
    response = client.get("/v1/admin/flags", headers={"Authorization": f"Bearer {token_read}"})
    assert response.status_code == 200

    # Test with admin scope - should succeed
    token_admin = _tok(["admin"])
    response = client.get("/v1/admin/flags", headers={"Authorization": f"Bearer {token_admin}"})
    assert response.status_code == 200

    # Test with insufficient scope - should fail
    token_insufficient = _tok(["user:profile"])
    response = client.get("/v1/admin/flags", headers={"Authorization": f"Bearer {token_insufficient}"})
    assert response.status_code == 403


def test_admin_errors_endpoint_scope(client):
    """Test that errors endpoint requires admin:read or admin scope"""
    # Test with admin:read scope - should succeed
    token_read = _tok(["admin:read"])
    response = client.get("/v1/admin/errors", headers={"Authorization": f"Bearer {token_read}"})
    assert response.status_code == 200

    # Test with admin scope - should succeed
    token_admin = _tok(["admin"])
    response = client.get("/v1/admin/errors", headers={"Authorization": f"Bearer {token_admin}"})
    assert response.status_code == 200

    # Test with insufficient scope - should fail
    token_insufficient = _tok(["user:profile"])
    response = client.get("/v1/admin/errors", headers={"Authorization": f"Bearer {token_insufficient}"})
    assert response.status_code == 403


def test_admin_tv_config_put_scope(client):
    """Test that TV config PUT endpoint requires admin:write or admin scope"""
    test_data = {"ambient_rotation": 45}

    # Test with admin:write scope - should succeed
    token_write = _tok(["admin:write"])
    response = client.put("/v1/admin/tv/config", json=test_data, headers={"Authorization": f"Bearer {token_write}"})
    assert response.status_code == 200

    # Test with admin scope - should succeed
    token_admin = _tok(["admin"])
    response = client.put("/v1/admin/tv/config", json=test_data, headers={"Authorization": f"Bearer {token_admin}"})
    assert response.status_code == 200

    # Test with admin:read only - should fail
    token_read = _tok(["admin:read"])
    response = client.put("/v1/admin/tv/config", json=test_data, headers={"Authorization": f"Bearer {token_read}"})
    assert response.status_code == 403


def test_admin_vector_store_bootstrap_scope(client):
    """Test that vector store bootstrap requires admin:write or admin scope"""
    # Test with admin:write scope - should succeed
    token_write = _tok(["admin:write"])
    response = client.post("/v1/admin/vector_store/bootstrap", headers={"Authorization": f"Bearer {token_write}"})
    assert response.status_code == 200

    # Test with admin scope - should succeed
    token_admin = _tok(["admin"])
    response = client.post("/v1/admin/vector_store/bootstrap", headers={"Authorization": f"Bearer {token_admin}"})
    assert response.status_code == 200

    # Test with admin:read only - should fail
    token_read = _tok(["admin:read"])
    response = client.post("/v1/admin/vector_store/bootstrap", headers={"Authorization": f"Bearer {token_read}"})
    assert response.status_code == 403


def test_user_profile_endpoint_scope(client):
    """Test that user profile endpoint requires user:profile scope"""
    # Test with user:profile scope - should succeed
    token_profile = _tok(["user:profile"])
    response = client.get("/v1/admin/users/me", headers={"Authorization": f"Bearer {token_profile}"})
    assert response.status_code == 200

    # Test with admin scope - should succeed (admin can access user profile)
    token_admin = _tok(["admin"])
    response = client.get("/v1/admin/users/me", headers={"Authorization": f"Bearer {token_admin}"})
    assert response.status_code == 200

    # Test with insufficient scope - should fail
    token_insufficient = _tok(["admin:read"])
    response = client.get("/v1/admin/users/me", headers={"Authorization": f"Bearer {token_insufficient}"})
    assert response.status_code == 403


def test_scope_combination_scenarios(client):
    """Test various scope combination scenarios"""
    # Test multiple scopes including required one
    token_multi = _tok(["admin:read", "user:profile"])
    response = client.get("/v1/admin/config", headers={"Authorization": f"Bearer {token_multi}"})
    assert response.status_code == 200

    # Test empty scope list
    token_empty = _tok([])
    response = client.get("/v1/admin/config", headers={"Authorization": f"Bearer {token_empty}"})
    assert response.status_code == 403

    # Test invalid scope format
    token_invalid = _tok(["invalid-scope"])
    response = client.get("/v1/admin/config", headers={"Authorization": f"Bearer {token_invalid}"})
    assert response.status_code == 403


def test_scope_inheritance_admin_full_access(client):
    """Test that admin scope provides access to all admin endpoints"""
    token_admin = _tok(["admin"])

    # Test all admin endpoints with admin scope
    endpoints = [
        "/v1/admin/config",
        "/v1/admin/metrics",
        "/v1/admin/system/status",
        "/v1/admin/flags",
        "/v1/admin/errors"
    ]

    for endpoint in endpoints:
        response = client.get(endpoint, headers={"Authorization": f"Bearer {token_admin}"})
        assert response.status_code == 200, f"Admin should access {endpoint}"


def test_scope_separation_read_vs_write(client):
    """Test that read and write scopes are properly separated"""
    # Test that admin:read allows reads but not writes
    token_read = _tok(["admin:read"])

    # Read operations should work
    read_endpoints = [
        "/v1/admin/config",
        "/v1/admin/metrics",
        "/v1/admin/system/status"
    ]

    for endpoint in read_endpoints:
        response = client.get(endpoint, headers={"Authorization": f"Bearer {token_read}"})
        assert response.status_code == 200, f"admin:read should allow GET {endpoint}"

    # Write operations should fail
    write_endpoints = [
        ("/v1/admin/config", "POST"),
        ("/v1/admin/tv/config", "PUT"),
        ("/v1/admin/vector_store/bootstrap", "POST")
    ]

    for endpoint, method in write_endpoints:
        if method == "POST":
            response = client.post(endpoint, headers={"Authorization": f"Bearer {token_read}"})
        elif method == "PUT":
            response = client.put(endpoint, json={}, headers={"Authorization": f"Bearer {token_read}"})
        assert response.status_code == 403, f"admin:read should not allow {method} {endpoint}"


def test_expired_token_handling(client):
    """Test that expired tokens are properly rejected"""
    # Create expired token
    key = os.environ.get("JWT_SECRET", "x" * 64)
    expired_time = int(time.time()) - 60  # 1 minute ago
    payload = {
        "sub": "test-user",
        "iat": expired_time,
        "exp": expired_time + 30,  # Already expired
        "scopes": ["admin"]
    }
    expired_token = jwt.encode(payload, key, algorithm="HS256")

    response = client.get("/v1/admin/config", headers={"Authorization": f"Bearer {expired_token}"})
    assert response.status_code == 401


def test_malformed_token_handling(client):
    """Test that malformed tokens are properly rejected"""
    response = client.get("/v1/admin/config", headers={"Authorization": "Bearer malformed-token"})
    assert response.status_code == 401

    response = client.get("/v1/admin/config", headers={"Authorization": "NotBearer token"})
    assert response.status_code == 401


def test_scope_case_sensitivity(client):
    """Test that scope matching is case sensitive"""
    # Test with lowercase scopes (assuming our system is case-sensitive)
    token_lowercase = _tok(["admin:read"])
    response = client.get("/v1/admin/config", headers={"Authorization": f"Bearer {token_lowercase}"})
    assert response.status_code == 200

    # Test with uppercase scopes
    token_uppercase = _tok(["ADMIN:READ"])
    response = client.get("/v1/admin/config", headers={"Authorization": f"Bearer {token_uppercase}"})
    # This should fail if our system is case-sensitive
    assert response.status_code in [401, 403]
