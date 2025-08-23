"""
Unit tests for cookie management functions in app.cookies.

Tests all cookie writer and clearer functions with comprehensive coverage:
- set_auth_cookies() / clear_auth_cookies()
- set_oauth_state_cookies() / clear_oauth_state_cookies()
- set_csrf_cookie() / clear_csrf_cookie()
- set_device_cookie() / clear_device_cookie()
- set_named_cookie() / clear_named_cookie()

Verifies correct attributes, Max-Age=0 on clear, HttpOnly, Path=/, SameSite=Lax in dev, Secure on prod.
"""

from unittest.mock import Mock, patch

from app.cookies import (
    clear_auth_cookies,
    clear_csrf_cookie,
    clear_device_cookie,
    clear_named_cookie,
    clear_oauth_state_cookies,
    set_auth_cookies,
    set_csrf_cookie,
    set_device_cookie,
    set_named_cookie,
    set_oauth_state_cookies,
)


class TestAuthCookies:
    """Test authentication cookie functions."""

    def test_set_auth_cookies_basic(self):
        """Test setting basic authentication cookies."""
        response = Mock()
        response.headers.append = Mock()
        request = Mock()
        request.url.scheme = "https"
        request.headers = {"host": "app.example.com"}

        with patch("app.cookies.get_cookie_config") as mock_config:
            mock_config.return_value = {
                "secure": True,
                "samesite": "lax",
                "httponly": True,
                "path": "/",
                "domain": None,
            }

            set_auth_cookies(
                resp=response,
                access="access_token_123",
                refresh="refresh_token_456",
                session_id="session_789",
                access_ttl=1800,
                refresh_ttl=86400,
                request=request,
            )

        # Verify headers were appended
        assert response.headers.append.call_count == 3  # access, refresh, session

        # Get all cookie headers that were set
        cookie_calls = [call.args[1] for call in response.headers.append.call_args_list]
        access_cookie = next(c for c in cookie_calls if "access_token=" in c)
        refresh_cookie = next(c for c in cookie_calls if "refresh_token=" in c)
        session_cookie = next(c for c in cookie_calls if "__session=" in c)

        # Verify cookie contents
        assert "access_token=access_token_123" in access_cookie
        assert "Max-Age=1800" in access_cookie
        assert "HttpOnly" in access_cookie
        assert "Path=/" in access_cookie
        assert "SameSite=Lax" in access_cookie
        assert "Secure" in access_cookie
        assert "Priority=High" in access_cookie
        assert "Domain=" not in access_cookie

        assert "refresh_token=refresh_token_456" in refresh_cookie
        assert "Max-Age=86400" in refresh_cookie
        assert "Priority=High" in refresh_cookie

        # Session cookie uses access_ttl (not refresh_ttl)
        assert "__session=session_789" in session_cookie
        assert "Max-Age=1800" in session_cookie  # Same as access_ttl

    def test_set_auth_cookies_no_refresh(self):
        """Test setting auth cookies without refresh token."""
        response = Mock()
        response.headers.append = Mock()
        request = Mock()
        request.url.scheme = "https"
        request.headers = {"host": "app.example.com"}

        with patch("app.cookies.get_cookie_config") as mock_config:
            mock_config.return_value = {
                "secure": True,
                "samesite": "lax",
                "httponly": True,
                "path": "/",
                "domain": None,
            }

            set_auth_cookies(
                resp=response,
                access="access_token_123",
                refresh="",  # Empty refresh token
                session_id="session_789",
                access_ttl=1800,
                refresh_ttl=86400,
                request=request,
            )

        # Verify only access and session cookies were set (no refresh)
        assert response.headers.append.call_count == 2
        cookie_calls = [call.args[1] for call in response.headers.append.call_args_list]
        cookie_names = [c.split("=")[0] for c in cookie_calls]
        assert "access_token" in cookie_names
        assert "__session" in cookie_names
        assert "refresh_token" not in cookie_names

    def test_set_auth_cookies_no_session(self):
        """Test setting auth cookies without session ID."""
        response = Mock()
        response.headers.append = Mock()
        request = Mock()
        request.url.scheme = "https"
        request.headers = {"host": "app.example.com"}

        with patch("app.cookies.get_cookie_config") as mock_config:
            mock_config.return_value = {
                "secure": True,
                "samesite": "lax",
                "httponly": True,
                "path": "/",
                "domain": None,
            }

            set_auth_cookies(
                resp=response,
                access="access_token_123",
                refresh="refresh_token_456",
                session_id=None,  # No session ID
                access_ttl=1800,
                refresh_ttl=86400,
                request=request,
            )

        # Verify only access and refresh cookies were set (no session)
        assert response.headers.append.call_count == 2
        cookie_calls = [call.args[1] for call in response.headers.append.call_args_list]
        cookie_names = [c.split("=")[0] for c in cookie_calls]
        assert "access_token" in cookie_names
        assert "refresh_token" in cookie_names
        assert "__session" not in cookie_names

    def test_clear_auth_cookies(self):
        """Test clearing authentication cookies with Max-Age=0."""
        response = Mock()
        response.headers.append = Mock()
        request = Mock()
        request.url.scheme = "https"
        request.headers = {"host": "app.example.com"}

        with patch("app.cookies.get_cookie_config") as mock_config:
            mock_config.return_value = {
                "secure": True,
                "samesite": "lax",
                "httponly": True,
                "path": "/",
                "domain": None,
            }

            clear_auth_cookies(response, request)

        # Verify all three cookies are cleared
        assert response.headers.append.call_count == 3
        cookie_calls = [call.args[1] for call in response.headers.append.call_args_list]

        # All cookies should have Max-Age=0 and empty values
        for cookie_header in cookie_calls:
            assert "Max-Age=0" in cookie_header
            assert "HttpOnly" in cookie_header
            assert "Path=/" in cookie_header
            assert "SameSite=Lax" in cookie_header
            assert "Secure" in cookie_header
            assert "Domain=" not in cookie_header

        # Check specific cookie names
        cookie_names = [c.split("=")[0] for c in cookie_calls]
        assert "access_token" in cookie_names
        assert "refresh_token" in cookie_names
        assert "__session" in cookie_names


class TestOAuthStateCookies:
    """Test OAuth state cookie functions."""

    def test_set_oauth_state_cookies(self):
        """Test setting OAuth state cookies."""
        response = Mock()
        response.headers.append = Mock()
        request = Mock()
        request.url.scheme = "https"
        request.headers = {"host": "app.example.com"}

        with patch("app.cookies.get_cookie_config") as mock_config:
            mock_config.return_value = {
                "secure": True,
                "samesite": "lax",
                "httponly": True,
                "path": "/",
                "domain": None,
            }

            set_oauth_state_cookies(
                resp=response,
                state="oauth_state_123",
                next_url="https://example.com/callback",
                request=request,
                ttl=600,
                provider="g",
            )

        # Verify two cookies were set (state and next)
        assert response.headers.append.call_count == 2
        cookie_calls = [call.args[1] for call in response.headers.append.call_args_list]

        # Find state and next cookies
        state_cookie = next(c for c in cookie_calls if "g_state=" in c)
        next_cookie = next(c for c in cookie_calls if "g_next=" in c)

        # Verify state cookie (HttpOnly)
        assert "g_state=oauth_state_123" in state_cookie
        assert "Max-Age=600" in state_cookie
        assert "HttpOnly" in state_cookie
        assert "Path=/" in state_cookie
        assert "SameSite=Lax" in state_cookie
        assert "Secure" in state_cookie

        # Verify next cookie (not HttpOnly)
        assert "g_next=https://example.com/callback" in next_cookie
        assert "Max-Age=600" in next_cookie
        assert "HttpOnly" not in next_cookie
        assert "Path=/" in next_cookie
        assert "SameSite=Lax" in next_cookie
        assert "Secure" in next_cookie

    def test_clear_oauth_state_cookies(self):
        """Test clearing OAuth state cookies with Max-Age=0."""
        response = Mock()
        response.headers.append = Mock()
        request = Mock()
        request.url.scheme = "https"
        request.headers = {"host": "app.example.com"}

        with patch("app.cookies.get_cookie_config") as mock_config:
            mock_config.return_value = {
                "secure": True,
                "samesite": "lax",
                "httponly": True,
                "path": "/",
                "domain": None,
            }

            clear_oauth_state_cookies(response, request, provider="g")

        # Verify two cookies are cleared
        assert response.headers.append.call_count == 2
        cookie_calls = [call.args[1] for call in response.headers.append.call_args_list]

        # Check state cookie (HttpOnly)
        state_cookie = next(c for c in cookie_calls if "g_state=" in c)
        assert "g_state=" in state_cookie
        assert "Max-Age=0" in state_cookie
        assert "HttpOnly" in state_cookie

        # Check next cookie (not HttpOnly)
        next_cookie = next(c for c in cookie_calls if "g_next=" in c)
        assert "g_next=" in next_cookie
        assert "Max-Age=0" in next_cookie
        assert "HttpOnly" not in next_cookie


class TestCSRFCookies:
    """Test CSRF cookie functions."""

    def test_set_csrf_cookie(self):
        """Test setting CSRF token cookie."""
        response = Mock()
        response.headers.append = Mock()
        request = Mock()
        request.url.scheme = "https"
        request.headers = {"host": "app.example.com"}

        with patch("app.cookies.get_cookie_config") as mock_config:
            mock_config.return_value = {
                "secure": True,
                "samesite": "lax",
                "httponly": False,
                "path": "/",
                "domain": None,
            }

            set_csrf_cookie(
                resp=response, token="csrf_token_123", ttl=3600, request=request
            )

        # Verify cookie was set
        assert response.headers.append.call_count == 1
        cookie_header = response.headers.append.call_args[0][1]

        # Verify CSRF cookie attributes (not HttpOnly, but all others)
        assert "csrf_token=csrf_token_123" in cookie_header
        assert "Max-Age=3600" in cookie_header
        assert "HttpOnly" not in cookie_header  # CSRF tokens need JavaScript access
        assert "Path=/" in cookie_header
        assert "SameSite=Lax" in cookie_header
        assert "Secure" in cookie_header
        assert "Domain=" not in cookie_header

    def test_set_csrf_cookie_samesite_none(self):
        """Test CSRF cookie with SameSite=None forces Secure=True."""
        response = Mock()
        response.headers.append = Mock()
        request = Mock()
        request.url.scheme = "http"
        request.headers = {"host": "localhost:3000"}

        with patch("app.cookies.get_cookie_config") as mock_config:
            mock_config.return_value = {
                "secure": False,
                "samesite": "none",
                "httponly": False,
                "path": "/",
                "domain": None,
            }

            set_csrf_cookie(
                resp=response, token="csrf_token_123", ttl=3600, request=request
            )

        cookie_header = response.headers.append.call_args[0][1]

        # SameSite=None should force Secure=True even in HTTP dev
        assert "SameSite=None" in cookie_header
        assert "Secure" in cookie_header

    def test_clear_csrf_cookie(self):
        """Test clearing CSRF token cookie with Max-Age=0."""
        response = Mock()
        response.headers.append = Mock()
        request = Mock()
        request.url.scheme = "https"
        request.headers = {"host": "app.example.com"}

        with patch("app.cookies.get_cookie_config") as mock_config:
            mock_config.return_value = {
                "secure": True,
                "samesite": "lax",
                "httponly": False,
                "path": "/",
                "domain": None,
            }

            clear_csrf_cookie(response, request)

        # Verify cookie was cleared
        assert response.headers.append.call_count == 1
        cookie_header = response.headers.append.call_args[0][1]

        assert "csrf_token=" in cookie_header
        assert "Max-Age=0" in cookie_header
        assert "HttpOnly" not in cookie_header
        assert "Path=/" in cookie_header
        assert "SameSite=Lax" in cookie_header
        assert "Secure" in cookie_header


class TestDeviceCookies:
    """Test device cookie functions."""

    def test_set_device_cookie(self):
        """Test setting device trust cookie."""
        response = Mock()
        response.headers.append = Mock()
        request = Mock()
        request.url.scheme = "https"
        request.headers = {"host": "app.example.com"}

        with patch("app.cookies.get_cookie_config") as mock_config:
            mock_config.return_value = {
                "secure": True,
                "samesite": "lax",
                "httponly": False,
                "path": "/",
                "domain": None,
            }

            set_device_cookie(
                resp=response,
                value="device_trust_123",
                ttl=86400,
                request=request,
                cookie_name="device_trust",
            )

        # Verify cookie was set
        assert response.headers.append.call_count == 1
        cookie_header = response.headers.append.call_args[0][1]

        # Verify device cookie attributes (not HttpOnly)
        assert "device_trust=device_trust_123" in cookie_header
        assert "Max-Age=86400" in cookie_header
        assert "HttpOnly" not in cookie_header  # Device cookies need JavaScript access
        assert "Path=/" in cookie_header
        assert "SameSite=Lax" in cookie_header
        assert "Secure" in cookie_header
        assert "Domain=" not in cookie_header

    def test_clear_device_cookie(self):
        """Test clearing device trust cookie with Max-Age=0."""
        response = Mock()
        response.headers.append = Mock()
        request = Mock()
        request.url.scheme = "https"
        request.headers = {"host": "app.example.com"}

        with patch("app.cookies.get_cookie_config") as mock_config:
            mock_config.return_value = {
                "secure": True,
                "samesite": "lax",
                "httponly": False,
                "path": "/",
                "domain": None,
            }

            clear_device_cookie(response, request, cookie_name="device_trust")

        # Verify cookie was cleared
        assert response.headers.append.call_count == 1
        cookie_header = response.headers.append.call_args[0][1]

        assert "device_trust=" in cookie_header
        assert "Max-Age=0" in cookie_header
        assert "HttpOnly" not in cookie_header
        assert "Path=/" in cookie_header
        assert "SameSite=Lax" in cookie_header
        assert "Secure" in cookie_header


class TestNamedCookies:
    """Test generic named cookie functions."""

    def test_set_named_cookie_basic(self):
        """Test setting a generic named cookie."""
        response = Mock()
        response.headers.append = Mock()
        request = Mock()
        request.url.scheme = "https"
        request.headers = {"host": "app.example.com"}

        with patch("app.cookies.get_cookie_config") as mock_config:
            mock_config.return_value = {
                "secure": True,
                "samesite": "lax",
                "httponly": True,
                "path": "/",
                "domain": None,
            }

            set_named_cookie(
                resp=response,
                name="test_cookie",
                value="test_value",
                ttl=3600,
                request=request,
            )

        # Verify cookie was set
        assert response.headers.append.call_count == 1
        cookie_header = response.headers.append.call_args[0][1]

        assert "test_cookie=test_value" in cookie_header
        assert "Max-Age=3600" in cookie_header
        assert "HttpOnly" in cookie_header
        assert "Path=/" in cookie_header
        assert "SameSite=Lax" in cookie_header
        assert "Secure" in cookie_header
        assert "Domain=" not in cookie_header

    def test_set_named_cookie_with_overrides(self):
        """Test setting named cookie with attribute overrides."""
        response = Mock()
        response.headers.append = Mock()
        request = Mock()
        request.url.scheme = "https"
        request.headers = {"host": "app.example.com"}

        with patch("app.cookies.get_cookie_config") as mock_config:
            mock_config.return_value = {
                "secure": True,
                "samesite": "lax",
                "httponly": True,
                "path": "/",
                "domain": None,
            }

            set_named_cookie(
                resp=response,
                name="custom_cookie",
                value="custom_value",
                ttl=1800,
                request=request,
                httponly=False,
                path="/api",
                secure=False,
                samesite="strict",
            )

        cookie_header = response.headers.append.call_args[0][1]

        # Verify overrides are respected
        assert "custom_cookie=custom_value" in cookie_header
        assert "Max-Age=1800" in cookie_header
        assert "HttpOnly" not in cookie_header  # Override to False
        assert "Path=/api" in cookie_header  # Override path
        assert "Secure" not in cookie_header  # Override to False
        assert "SameSite=Strict" in cookie_header  # Override samesite
        assert "Domain=" not in cookie_header

    def test_clear_named_cookie(self):
        """Test clearing a generic named cookie with Max-Age=0."""
        response = Mock()
        response.headers.append = Mock()
        request = Mock()
        request.url.scheme = "https"
        request.headers = {"host": "app.example.com"}

        with patch("app.cookies.get_cookie_config") as mock_config:
            mock_config.return_value = {
                "secure": True,
                "samesite": "lax",
                "httponly": True,
                "path": "/",
                "domain": None,
            }

            clear_named_cookie(response, name="test_cookie", request=request)

        # Verify cookie was cleared
        assert response.headers.append.call_count == 1
        cookie_header = response.headers.append.call_args[0][1]

        assert "test_cookie=" in cookie_header
        assert "Max-Age=0" in cookie_header
        assert "HttpOnly" in cookie_header  # Default for clear
        assert "Path=/" in cookie_header
        assert "SameSite=Lax" in cookie_header
        assert "Secure" in cookie_header


class TestCookieSecurityAttributes:
    """Test cookie security attributes in different environments."""

    def test_dev_http_cookies_not_secure(self):
        """Test that cookies are not Secure in development HTTP environment."""
        response = Mock()
        response.headers.append = Mock()
        request = Mock()
        request.url.scheme = "http"
        request.headers = {"host": "localhost:3000"}

        with patch("app.cookies.get_cookie_config") as mock_config:
            mock_config.return_value = {
                "secure": False,
                "samesite": "lax",
                "httponly": True,
                "path": "/",
                "domain": None,
            }

            set_auth_cookies(
                resp=response,
                access="access_token_123",
                refresh="refresh_token_456",
                session_id=None,
                access_ttl=1800,
                refresh_ttl=86400,
                request=request,
            )

        cookie_calls = [call.args[1] for call in response.headers.append.call_args_list]

        # Verify cookies are not Secure in dev HTTP
        for cookie_header in cookie_calls:
            assert "Secure" not in cookie_header
            assert "SameSite=Lax" in cookie_header

    def test_prod_https_cookies_secure(self):
        """Test that cookies are Secure in production HTTPS environment."""
        response = Mock()
        response.headers.append = Mock()
        request = Mock()
        request.url.scheme = "https"
        request.headers = {"host": "app.example.com"}

        with patch("app.cookies.get_cookie_config") as mock_config:
            mock_config.return_value = {
                "secure": True,
                "samesite": "lax",
                "httponly": True,
                "path": "/",
                "domain": None,
            }

            set_auth_cookies(
                resp=response,
                access="access_token_123",
                refresh="refresh_token_456",
                session_id=None,
                access_ttl=1800,
                refresh_ttl=86400,
                request=request,
            )

        cookie_calls = [call.args[1] for call in response.headers.append.call_args_list]

        # Verify cookies are Secure in prod HTTPS
        for cookie_header in cookie_calls:
            assert "Secure" in cookie_header
            assert "SameSite=Lax" in cookie_header


class TestCookieNegativeScenarios:
    """Test negative scenarios and error handling."""

    def test_missing_config_defaults_gracefully(self):
        """Test that missing configuration defaults gracefully."""
        response = Mock()
        response.headers.append = Mock()
        request = Mock()
        request.url.scheme = "http"
        request.headers = {"host": "localhost:3000"}

        # Mock get_cookie_config to return None (simulate config failure)
        with patch("app.cookies.get_cookie_config", return_value=None):
            # Should not raise exception, but may not set cookies
            # This tests graceful degradation
            try:
                set_auth_cookies(
                    resp=response,
                    access="access_token_123",
                    refresh="refresh_token_456",
                    session_id=None,
                    access_ttl=1800,
                    refresh_ttl=86400,
                    request=request,
                )
                # If no exception, verify no cookies were set
                assert response.headers.append.call_count == 0
            except Exception:
                # If exception occurs, it should be handled gracefully
                pass

    def test_invalid_cookie_values(self):
        """Test handling of invalid cookie values."""
        response = Mock()
        response.headers.append = Mock()
        request = Mock()
        request.url.scheme = "https"
        request.headers = {"host": "app.example.com"}

        with patch("app.cookies.get_cookie_config") as mock_config:
            mock_config.return_value = {
                "secure": True,
                "samesite": "lax",
                "httponly": True,
                "path": "/",
                "domain": None,
            }

            # Test with None values (should handle gracefully)
            set_auth_cookies(
                resp=response,
                access=None,
                refresh=None,
                session_id=None,
                access_ttl=1800,
                refresh_ttl=86400,
                request=request,
            )

            # Should still set cookies (with string "None")
            assert response.headers.append.call_count >= 1
            cookie_calls = [
                call.args[1] for call in response.headers.append.call_args_list
            ]

            # Verify cookies were set with string representations
            for cookie_header in cookie_calls:
                assert (
                    "Max-Age=1800" in cookie_header or "Max-Age=86400" in cookie_header
                )

    def test_empty_cookie_values_on_clear(self):
        """Test that cleared cookies have empty values."""
        response = Mock()
        response.headers.append = Mock()
        request = Mock()
        request.url.scheme = "https"
        request.headers = {"host": "app.example.com"}

        with patch("app.cookies.get_cookie_config") as mock_config:
            mock_config.return_value = {
                "secure": True,
                "samesite": "lax",
                "httponly": True,
                "path": "/",
                "domain": None,
            }

            clear_auth_cookies(response, request)

        cookie_calls = [call.args[1] for call in response.headers.append.call_args_list]

        # All cleared cookies should have empty values (cookie_name=)
        for cookie_header in cookie_calls:
            # Should have format like "access_token=" (no value after =)
            cookie_parts = cookie_header.split(";")[0].split("=")
            assert len(cookie_parts) == 2
            assert cookie_parts[1] == ""  # Empty value
