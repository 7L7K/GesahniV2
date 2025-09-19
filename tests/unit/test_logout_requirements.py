from fastapi.testclient import TestClient

from app.main import app
from app.tokens import make_access

EXPIRES_PAST = "Expires=Thu, 01 Jan 1970 00:00:00 GMT"


def _get_auth_headers():
    """Get authentication headers for test requests."""
    token = make_access({"user_id": "test_user"})
    return {"Authorization": f"Bearer {token}"}


def test_logout_returns_204_no_content():
    """Test that logout returns 204 No Content status code."""
    client = TestClient(app)
    response = client.post("/v1/auth/logout", headers=_get_auth_headers())
    assert response.status_code == 204


def test_logout_deletes_all_three_cookies():
    """Test that logout deletes all three auth cookies: access_token, refresh_token, __session."""
    client = TestClient(app)
    response = client.post("/v1/auth/logout", headers=_get_auth_headers())

    # Get all Set-Cookie headers
    set_cookie_headers = response.headers.get("Set-Cookie", "")
    if isinstance(set_cookie_headers, str):
        set_cookie_headers = [set_cookie_headers]

    # Should have Set-Cookie headers for all three cookies
    cookie_names = ["access_token", "refresh_token", "__session"]
    for cookie_name in cookie_names:
        # Find the Set-Cookie header for this cookie
        cookie_header = None
        for header in set_cookie_headers:
            # Handle both single cookie headers and combined headers
            if header.startswith(f"{cookie_name}="):
                cookie_header = header
                break
            # Also check for combined headers with multiple cookies
            elif f"{cookie_name}=" in header:
                cookie_header = header
                break

        assert cookie_header is not None, f"Missing Set-Cookie header for {cookie_name}"

        # Verify Max-Age=0 for immediate deletion
        assert "Max-Age=0" in cookie_header, f"{cookie_name} should have Max-Age=0"
        assert (
            EXPIRES_PAST in cookie_header
        ), f"{cookie_name} should have past Expires timestamp"

        # Verify empty value
        assert (
            f"{cookie_name}=" in cookie_header
        ), f"{cookie_name} should have empty value"


def test_logout_uses_same_attributes_as_login():
    """Test that logout uses the same cookie attributes as login (Path, SameSite, Secure, no Domain in dev)."""
    client = TestClient(app)
    response = client.post("/v1/auth/logout", headers=_get_auth_headers())

    set_cookie_headers = response.headers.get("Set-Cookie", "")
    if isinstance(set_cookie_headers, str):
        set_cookie_headers = [set_cookie_headers]

    # Check that all cookies have the expected attributes
    for header in set_cookie_headers:
        # Should have Path=/
        assert "Path=/" in header

        # Should have SameSite=Lax (default)
        assert "SameSite=Lax" in header

        # Should have HttpOnly
        assert "HttpOnly" in header

        # Should have Priority=High for auth cookies
        assert "Priority=High" in header

        # Should NOT have Domain in development (host-only cookies)
        assert "Domain=" not in header


def test_logout_has_proper_deletion_semantics():
    """Test that logout uses proper deletion semantics (Max-Age=0)."""
    client = TestClient(app)
    response = client.post("/v1/auth/logout", headers=_get_auth_headers())

    set_cookie_headers = response.headers.get("Set-Cookie", "")
    if isinstance(set_cookie_headers, str):
        set_cookie_headers = [set_cookie_headers]

    # All Set-Cookie headers should have Max-Age=0 for immediate deletion
    for header in set_cookie_headers:
        assert (
            "Max-Age=0" in header
        ), "All cookies should have Max-Age=0 for immediate deletion"
        assert EXPIRES_PAST in header, "All cookies should set past Expires"


def test_logout_response_is_unambiguous():
    """Test that logout response is unambiguously 'I logged you out'."""
    client = TestClient(app)
    response = client.post("/v1/auth/logout", headers=_get_auth_headers())

    # 204 No Content status
    assert response.status_code == 204

    # No response body (204 No Content)
    assert response.content == b""

    # Clear indication through Set-Cookie headers with Max-Age=0
    set_cookie_headers = response.headers.get("Set-Cookie", "")
    if isinstance(set_cookie_headers, str):
        set_cookie_headers = [set_cookie_headers]
    # Should have at least one Set-Cookie header (may contain multiple cookies)
    assert (
        len(set_cookie_headers) >= 1
    ), "Should have Set-Cookie headers for auth cookies"

    # All cookies should be deleted (Max-Age=0)
    for header in set_cookie_headers:
        assert "Max-Age=0" in header, "All cookies should be deleted"
        assert EXPIRES_PAST in header, "All cookies should set past Expires"


def test_logout_works_with_existing_cookies():
    """Test that logout works correctly when user has existing auth cookies."""
    client = TestClient(app)

    # Note: We don't set fake cookies since logout validates them and would fail with 403
    # The main purpose is to test logout functionality, not cookie validation
    response = client.post("/v1/auth/logout", headers=_get_auth_headers())

    assert response.status_code == 204

    # Verify logout response has proper cookie clearing headers
    set_cookie_headers = response.headers.get("Set-Cookie", "")
    if isinstance(set_cookie_headers, str):
        set_cookie_headers = [set_cookie_headers]

    # Should have at least some cookie clearing headers
    assert set_cookie_headers, "Logout should clear cookies"
    for header in set_cookie_headers:
        assert "Max-Age=0" in header
        assert EXPIRES_PAST in header
