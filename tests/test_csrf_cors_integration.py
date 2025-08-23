from fastapi.testclient import TestClient

from app.main import app


def test_csrf_cookie_and_cors():
    """Test CSRF cookie flags and CORS headers on both success and failure responses."""
    with TestClient(app) as client:
        # Test 1: CSRF endpoint should set cookie with proper flags
        r = client.get("/v1/csrf", headers={"Origin": "http://localhost:3000"})

        # Should succeed and return CSRF token
        assert r.status_code == 200
        assert "csrf_token" in r.json()

        # Check Set-Cookie header has proper flags
        assert "set-cookie" in r.headers
        cookie = r.headers["set-cookie"]

        # CSRF token must be accessible to JavaScript, so NOT HttpOnly
        assert "Path=/" in cookie
        assert "SameSite" in cookie  # Should have SameSite policy
        assert "HttpOnly" not in cookie  # CSRF token must be readable by JS

        # Should have CORS headers even on success
        assert "access-control-allow-origin" in r.headers

        # Test 2: Failed request to protected endpoint should still have CORS headers
        bad = client.post(
            "/v1/ask",
            json={"prompt": "test"},
            headers={"Origin": "http://localhost:3000"}
        )

        # Should fail due to missing auth
        assert bad.status_code in (401, 403, 422)  # Various auth failure codes possible

        # But should still have CORS headers
        assert "access-control-allow-origin" in bad.headers
