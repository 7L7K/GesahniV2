"""Test helpers for HTTP requests with CSRF handling using unified constants."""

from typing import Dict, Any, Optional, Union
from fastapi.testclient import TestClient

from app.auth.constants import ACCESS_COOKIE, REFRESH_COOKIE, CSRF_COOKIE
from .auth import mint_access_token


def get_csrf_token(client: TestClient) -> tuple[Dict[str, str], str]:
    """Fetch CSRF token and cookies from the server.

    Returns:
        tuple: (csrf_cookies_dict, csrf_token)
    """
    # Try the new auth endpoint first
    r = client.get("/v1/auth/csrf", allow_redirects=True)
    if r.status_code == 404:
        # Fall back to legacy endpoint
        r = client.get("/csrf", allow_redirects=True)

    assert r.status_code == 200, f"Failed to get CSRF token: {r.status_code} {r.text}"

    csrf_token = r.json()["csrf_token"]

    # Extract CSRF cookies from response
    csrf_cookies = {}
    for cookie_name in [CSRF_COOKIE, "g_csrf_token"]:
        if cookie_name in client.cookies:
            csrf_cookies[cookie_name] = client.cookies[cookie_name]

    return csrf_cookies, csrf_token


def has_auth_cookies(client: TestClient) -> bool:
    """Check if client has authentication cookies.

    Returns:
        True if client has access or refresh cookies, False otherwise
    """
    return any(
        name in client.cookies
        for name in [ACCESS_COOKIE, REFRESH_COOKIE, "session_id", "g_access_token"]
    )


def auth_request(
    client: TestClient,
    method: str,
    url: str,
    json: Optional[Dict[str, Any]] = None,
    data: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    allow_redirects: bool = True,
    **kwargs
) -> Any:
    """Make an authenticated request with automatic CSRF handling.

    If client has auth cookies, automatically fetch CSRF token and inject header.
    If not authenticated, skip CSRF enforcement.
    """
    # Check if client has auth cookies
    if has_auth_cookies(client) and method.upper() in {"POST", "PUT", "PATCH", "DELETE"}:
        try:
            csrf_cookies, csrf_token = get_csrf_token(client)
            request_headers = headers or {}
            request_headers["X-CSRF-Token"] = csrf_token
            headers = request_headers
        except Exception:
            # If CSRF fetch fails, continue without it
            pass

    # Prepare request parameters
    request_kwargs = {"allow_redirects": allow_redirects, **kwargs}
    if json is not None:
        request_kwargs["json"] = json
    if data is not None:
        request_kwargs["data"] = data
    if headers:
        request_kwargs["headers"] = headers

    # Make the request
    return client.request(method, url, **request_kwargs)


def auth_get(
    client: TestClient,
    url: str,
    headers: Optional[Dict[str, str]] = None,
    allow_redirects: bool = True,
    **kwargs
) -> Any:
    """Make an authenticated GET request."""
    return auth_request(client, "GET", url, headers=headers, allow_redirects=allow_redirects, **kwargs)


def auth_post(
    client: TestClient,
    url: str,
    json: Optional[Dict[str, Any]] = None,
    data: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    allow_redirects: bool = True,
    **kwargs
) -> Any:
    """Make an authenticated POST request with automatic CSRF handling."""
    return auth_request(client, "POST", url, json=json, data=data, headers=headers, allow_redirects=allow_redirects, **kwargs)


def auth_put(
    client: TestClient,
    url: str,
    json: Optional[Dict[str, Any]] = None,
    data: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    allow_redirects: bool = True,
    **kwargs
) -> Any:
    """Make an authenticated PUT request with automatic CSRF handling."""
    return auth_request(client, "PUT", url, json=json, data=data, headers=headers, allow_redirects=allow_redirects, **kwargs)


def auth_patch(
    client: TestClient,
    url: str,
    json: Optional[Dict[str, Any]] = None,
    data: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    allow_redirects: bool = True,
    **kwargs
) -> Any:
    """Make an authenticated PATCH request with automatic CSRF handling."""
    return auth_request(client, "PATCH", url, json=json, data=data, headers=headers, allow_redirects=allow_redirects, **kwargs)


def auth_delete(
    client: TestClient,
    url: str,
    headers: Optional[Dict[str, str]] = None,
    allow_redirects: bool = True,
    **kwargs
) -> Any:
    """Make an authenticated DELETE request with automatic CSRF handling."""
    return auth_request(client, "DELETE", url, headers=headers, allow_redirects=allow_redirects, **kwargs)


def setup_auth_cookies(client: TestClient, user_id: str = "test_user") -> None:
    """Set up authentication cookies on test client.

    Args:
        client: TestClient instance
        user_id: User ID for the token
    """
    # Mint test tokens
    access_token = mint_access_token(user_id)

    # Import mint_refresh_token from auth helpers
    from .auth import mint_refresh_token
    refresh_token = mint_refresh_token(user_id)

    # Use the canonical cookie names that the app actually uses
    # Import here to avoid circular imports
    from app.cookie_names import GSNH_AT, GSNH_RT, GSNH_SESS

    # Set the access cookie
    client.cookies.set(GSNH_AT, access_token)
    # Set the refresh cookie
    client.cookies.set(GSNH_RT, refresh_token)
    # Set the session cookie (opaque value)
    client.cookies.set(GSNH_SESS, access_token)  # Use access token as session for simplicity


def setup_csrf_cookie(client: TestClient) -> str:
    """Set up CSRF cookie on test client.

    Returns:
        CSRF token that was set
    """
    # Get CSRF token from server
    _, csrf_token = get_csrf_token(client)

    # Manually set the CSRF cookie (normally done by middleware)
    client.cookies.set(CSRF_COOKIE, csrf_token)

    return csrf_token
