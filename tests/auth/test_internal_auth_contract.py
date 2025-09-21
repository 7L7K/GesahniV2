"""OpenAPI contract tests for internal auth consolidation.

These tests ensure that only canonical /v1/auth/* routes are exposed in the
OpenAPI schema and prevent regression to duplicate/competing auth handlers.
"""

import pytest
from fastapi.testclient import TestClient


def test_internal_auth_canonical_routes_only(app):
    """Ensure only canonical /v1/auth/* routes are exposed in OpenAPI schema."""
    client = TestClient(app)
    response = client.get("/openapi.json")
    assert response.status_code == 200
    
    openapi_json = response.json()
    paths = set(openapi_json["paths"].keys())
    
    # Canonical auth routes MUST be present
    required_canonical_routes = {
        "/v1/auth/login",
        "/v1/auth/logout", 
        "/v1/auth/refresh",
        "/v1/auth/register",
        "/v1/auth/logout_all",
        "/v1/auth/token",
        "/v1/auth/examples",
    }
    
    for route in required_canonical_routes:
        assert route in paths, f"Missing canonical route: {route}"
    
    # Legacy root-level routes must NOT be in schema (hidden by include_in_schema=False)
    forbidden_legacy_routes = {
        "/login",
        "/logout", 
        "/refresh",
        "/register",
    }
    
    for route in forbidden_legacy_routes:
        assert route not in paths, f"Legacy route {route} should not be in OpenAPI schema"
    
    # Competing /v1/* routes must NOT be in schema
    forbidden_v1_routes = {
        "/v1/login",
        "/v1/logout",
        "/v1/refresh", 
        "/v1/register",
    }
    
    for route in forbidden_v1_routes:
        assert route not in paths, f"Competing route {route} should not be in OpenAPI schema"


def test_internal_auth_single_login_handler():
    """Ensure only one login handler is defined in OpenAPI paths."""
    from fastapi.testclient import TestClient
    from app.main import app
    
    client = TestClient(app)
    response = client.get("/openapi.json")
    openapi_json = response.json()
    
    # Count login-related paths
    login_paths = [path for path in openapi_json["paths"].keys() if "login" in path]
    canonical_login_paths = [path for path in login_paths if path.startswith("/v1/auth/")]
    
    # Should have exactly one canonical login path
    assert "/v1/auth/login" in canonical_login_paths
    assert len([p for p in canonical_login_paths if p.endswith("/login")]) == 1, \
        f"Multiple login handlers found: {canonical_login_paths}"


def test_internal_auth_single_refresh_handler():
    """Ensure only one refresh handler is defined in OpenAPI paths."""
    from fastapi.testclient import TestClient
    from app.main import app
    
    client = TestClient(app)
    response = client.get("/openapi.json")
    openapi_json = response.json()
    
    # Count refresh-related paths
    refresh_paths = [path for path in openapi_json["paths"].keys() if "refresh" in path]
    canonical_refresh_paths = [path for path in refresh_paths if path.startswith("/v1/auth/")]
    
    # Should have exactly one canonical refresh path
    assert "/v1/auth/refresh" in canonical_refresh_paths
    auth_refresh_paths = [p for p in canonical_refresh_paths if p.endswith("/refresh")]
    assert len(auth_refresh_paths) == 1, \
        f"Multiple refresh handlers found: {auth_refresh_paths}"


def test_internal_auth_legacy_redirects_work():
    """Ensure legacy routes redirect to canonical paths with proper headers."""
    from fastapi.testclient import TestClient
    from app.main import app
    
    client = TestClient(app)
    
    # Test legacy root-level redirects
    legacy_routes = [
        ("/login", "/v1/auth/login"),
        ("/logout", "/v1/auth/logout"),
        ("/refresh", "/v1/auth/refresh"),
        ("/register", "/v1/auth/register"),
    ]
    
    for legacy_path, canonical_path in legacy_routes:
        response = client.post(legacy_path, follow_redirects=False)
        
        # Should be a 308 permanent redirect
        assert response.status_code == 308, f"{legacy_path} should return 308"
        
        # Should redirect to canonical path
        assert response.headers["location"] == canonical_path, \
            f"{legacy_path} should redirect to {canonical_path}"
        
        # Should have deprecation headers
        assert "Deprecation" in response.headers
        assert response.headers["Deprecation"] == "true"
        assert "Sunset" in response.headers
        assert "Link" in response.headers


@pytest.mark.integration 
def test_internal_auth_no_duplicate_handlers():
    """Integration test: ensure no duplicate auth handlers cause conflicts."""
    from fastapi.testclient import TestClient
    from app.main import app
    
    client = TestClient(app)
    
    # Test that canonical routes work (even without valid credentials)
    canonical_routes = ["/v1/auth/login", "/v1/auth/logout", "/v1/auth/refresh"]
    
    for route in canonical_routes:
        response = client.post(route)
        # Should not get 500 (internal server error from duplicate handlers)
        # Should get 400/401/422 (business logic errors)
        assert response.status_code != 500, \
            f"Route {route} returned 500 - possible duplicate handler conflict"
        assert response.status_code in {400, 401, 422}, \
            f"Route {route} should return 400/401/422, got {response.status_code}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
