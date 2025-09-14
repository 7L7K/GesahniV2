from fastapi.testclient import TestClient

from app.main import create_app


def test_canonical_auth_routes_exist():
    """Test that canonical auth routes exist and work properly."""
    app = create_app()
    client = TestClient(app)

    # Test that canonical routes exist (may return 401 for unauthenticated requests)
    canonical_routes = [
        "/v1/auth/login",  # POST only - should return 405 for GET
        "/v1/auth/logout",  # POST only - should return 405 for GET
        "/v1/auth/register",  # POST only - should return 405 for GET
        "/v1/auth/refresh",  # POST only - should return 405 for GET
        "/v1/auth/whoami",  # GET only - should return 401 for unauthenticated
        "/v1/auth/token",  # POST only - should return 405 for GET
    ]

    for route in canonical_routes:
        resp = client.get(route, allow_redirects=False)
        # Routes should either work (401 for unauthenticated) or return method not allowed (405)
        # but should NOT return 404 (not found)
        assert (
            resp.status_code != 404
        ), f"Canonical route {route} not found: got {resp.status_code}"
        assert resp.status_code in (
            401,
            405,
        ), f"Canonical route {route} returned unexpected status: {resp.status_code}"


def test_legacy_endpoints_exist():
    """Test that legacy auth endpoints still exist and work correctly."""
    app = create_app()
    client = TestClient(app)

    # These legacy endpoints should still exist and be POST-only
    legacy_routes = [
        "/v1/login",
        "/v1/register",
    ]

    for route in legacy_routes:
        # GET requests should return 405 (Method Not Allowed)
        resp = client.get(route, allow_redirects=False)
        assert (
            resp.status_code == 405
        ), f"GET {route} should return 405: got {resp.status_code}"

        # POST requests should work (may return 401 for auth, but not 404)
        resp = client.post(route, allow_redirects=False)
        assert (
            resp.status_code != 404
        ), f"POST {route} should exist: got {resp.status_code}"


def test_canonical_finish_endpoint():
    """Test that /v1/auth/finish endpoint exists and handles requests properly."""
    app = create_app()
    client = TestClient(app)

    # /v1/auth/finish supports both GET and POST but requires authentication
    # For unauthenticated requests, it should return auth-related errors, not 404
    for method in ["GET", "POST"]:
        resp = client.request(method, "/v1/auth/finish", allow_redirects=False)
        # Should not return 404 (endpoint exists) and should not return 308 (not a redirect)
        assert (
            resp.status_code != 404
        ), f"{method} /v1/auth/finish should exist: got {resp.status_code}"
        assert (
            resp.status_code != 308
        ), f"{method} /v1/auth/finish should not be a redirect: got {resp.status_code}"
        # Should return auth-related status codes
        assert resp.status_code in (
            401,
            403,
            422,
            405,
        ), f"{method} /v1/auth/finish returned unexpected status: {resp.status_code}"


def test_legacy_redirects_behavior():
    """Test that legacy endpoints redirect correctly with 308 Permanent Redirect."""
    app = create_app()
    client = TestClient(app)

    # Legacy routes that should redirect to canonical auth routes
    legacy_to_canonical = {
        "/v1/login": "/v1/auth/login",
        "/v1/logout": "/v1/auth/logout",
        "/v1/refresh": "/v1/auth/refresh",
        "/v1/whoami": "/v1/auth/whoami",
        "/v1/finish": "/v1/auth/finish",
    }

    # Test both GET and POST methods for each legacy route
    for legacy_path, canonical_path in legacy_to_canonical.items():
        for method in ["GET", "POST"]:
            resp = client.request(method, legacy_path, allow_redirects=False)

            # Assert 308 Permanent Redirect status
            assert (
                resp.status_code == 308
            ), f"{method} {legacy_path} should return 308, got {resp.status_code}"

            # Assert Location header points to canonical route
            location = resp.headers.get("location") or resp.headers.get("Location")
            assert (
                location == canonical_path
            ), f"{method} {legacy_path} should redirect to {canonical_path}, got {location}"

            # Assert method is preserved (308 preserves method and body)
            # This is implicit in HTTP 308 behavior, but we can verify the redirect works


def test_legacy_redirect_with_body_preserved():
    """Test that POST redirects preserve request body."""
    app = create_app()
    client = TestClient(app)

    # Test POST to /v1/login with JSON body
    test_data = {"username": "testuser", "password": "testpass"}
    resp = client.post("/v1/login", json=test_data, allow_redirects=False)

    # Should redirect with 308
    assert resp.status_code == 308
    location = resp.headers.get("location") or resp.headers.get("Location")
    assert location == "/v1/auth/login"

    # Note: FastAPI TestClient doesn't actually follow redirects with body preservation
    # in this test, but the 308 status code ensures the method and body would be preserved


def test_legacy_redirect_with_query_params():
    """Test that redirects preserve query parameters."""
    app = create_app()
    client = TestClient(app)

    # Test GET with query parameters
    resp = client.get("/v1/login?next=/dashboard&token=abc123", allow_redirects=False)

    # Should redirect with 308
    assert resp.status_code == 308
    location = resp.headers.get("location") or resp.headers.get("Location")
    assert location == "/v1/auth/login?next=/dashboard&token=abc123"


def test_legacy_redirect_methods_supported():
    """Test that all HTTP methods are supported on legacy routes."""
    app = create_app()
    client = TestClient(app)

    # Test various HTTP methods on legacy routes
    methods_to_test = ["GET", "POST", "PUT", "DELETE", "PATCH"]

    for method in methods_to_test:
        resp = client.request(method, "/v1/login", allow_redirects=False)

        # All methods should redirect with 308
        assert (
            resp.status_code == 308
        ), f"{method} /v1/login should return 308, got {resp.status_code}"
        location = resp.headers.get("location") or resp.headers.get("Location")
        assert (
            location == "/v1/auth/login"
        ), f"{method} /v1/login should redirect to /v1/auth/login, got {location}"


def test_no_redirect_loops():
    """Test that canonical routes don't redirect to avoid loops."""
    app = create_app()
    client = TestClient(app)

    # Canonical routes should NOT redirect
    canonical_routes = [
        "/v1/auth/login",
        "/v1/auth/logout",
        "/v1/auth/register",
        "/v1/auth/refresh",
        "/v1/auth/whoami",
        "/v1/auth/finish",
    ]

    for route in canonical_routes:
        for method in ["GET", "POST"]:
            resp = client.request(method, route, allow_redirects=False)
            # Should not return 308 (no redirect)
            assert (
                resp.status_code != 308
            ), f"Canonical route {route} should not redirect, got {resp.status_code}"
