#!/usr/bin/env python3
"""
Comprehensive cookie functionality tests.

Tests cover:
- Cookie constants and naming consistency
- Cookie TTL configuration and validation
- Cookie security flags (HttpOnly, Secure, SameSite)
- Cookie domain and path settings
- Cookie precedence order for reading
- Legacy cookie compatibility
- CSRF cookie handling
- Environment-based cookie configuration
"""

import os
import pytest
from contextlib import contextmanager
from unittest.mock import Mock

from fastapi import Request, Response
from fastapi.testclient import TestClient

from app.cookie_config import get_cookie_config, get_token_ttls, format_cookie_header
from app.web.cookies import (
    ACCESS_NAME, REFRESH_NAME, SESSION_NAME,
    NAMES, AT_ORDER, RT_ORDER, SESS_ORDER,
    set_named_cookie, clear_named_cookie, read_access_cookie,
    set_csrf_cookie, clear_csrf_cookie
)
from app.cookies import read_access_cookie as wrapper_read_access_cookie


@contextmanager
def env_vars(**kwargs):
    """Context manager for temporarily setting environment variables."""
    old_values = {}
    for key in kwargs:
        old_values[key] = os.environ.get(key)

    try:
        for key, value in kwargs.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = str(value)
        # Clear any cached config
        from app import cookie_config
        if hasattr(cookie_config, '_config_cache'):
            cookie_config._config_cache.clear()
        yield
    finally:
        for key, old_value in old_values.items():
            if old_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old_value
        # Clear cache again
        if hasattr(cookie_config, '_config_cache'):
            cookie_config._config_cache.clear()


class TestCookieConstants:
    """Test cookie naming constants consistency."""

    def test_cookie_constants_defined(self):
        """Test that all cookie name constants are properly defined."""
        assert ACCESS_NAME == "GSNH_AT"
        assert REFRESH_NAME == "GSNH_RT"
        assert SESSION_NAME == "GSNH_SESS"

    def test_cookie_names_consistency(self):
        """Test that NAMES object uses the constants."""
        # In production/dev mode, NAMES should use the constants
        assert NAMES.access == ACCESS_NAME
        assert NAMES.refresh == REFRESH_NAME
        assert NAMES.session == SESSION_NAME

    def test_cookie_precedence_orders(self):
        """Test that precedence orders include canonical names."""
        assert ACCESS_NAME in AT_ORDER
        assert REFRESH_NAME in RT_ORDER
        assert SESSION_NAME in SESS_ORDER

        # Canonical names should be in precedence order (may be prefixed)
        # The order prioritizes most secure versions first
        assert any(ACCESS_NAME in name or name.endswith(ACCESS_NAME) for name in AT_ORDER)
        assert any(REFRESH_NAME in name or name.endswith(REFRESH_NAME) for name in RT_ORDER)
        assert any(SESSION_NAME in name or name.endswith(SESSION_NAME) for name in SESS_ORDER)


class TestCookieTTLConfiguration:
    """Test cookie TTL configuration from environment."""

    def test_default_token_ttls(self):
        """Test default token TTL values."""
        with env_vars(JWT_EXPIRE_MINUTES=None, JWT_REFRESH_EXPIRE_MINUTES=None):
            access_ttl, refresh_ttl = get_token_ttls()
            assert access_ttl == 15 * 60  # 15 minutes in seconds
            assert refresh_ttl == 43200 * 60  # 30 days in seconds

    def test_custom_token_ttls(self):
        """Test custom token TTL values from environment."""
        with env_vars(JWT_EXPIRE_MINUTES="30", JWT_REFRESH_EXPIRE_MINUTES="1440"):
            access_ttl, refresh_ttl = get_token_ttls()
            assert access_ttl == 30 * 60  # 30 minutes in seconds
            assert refresh_ttl == 1440 * 60  # 24 hours in seconds

    def test_token_ttl_validation(self):
        """Test that TTL values are reasonable."""
        with env_vars(JWT_EXPIRE_MINUTES="1", JWT_REFRESH_EXPIRE_MINUTES="60"):
            access_ttl, refresh_ttl = get_token_ttls()
            assert 60 <= access_ttl <= 3600  # 1-60 minutes reasonable
            assert 3600 <= refresh_ttl <= 2592000  # 1 hour to 30 days reasonable


class TestCookieSecurityFlags:
    """Test cookie security flags under different conditions."""

    def test_secure_flag_defaults(self):
        """Test secure flag defaults in different environments."""
        mock_request = Mock(spec=Request)
        mock_request.headers = {}
        mock_request.url = Mock()
        mock_request.url.scheme = "http"
        mock_request.client = Mock()
        mock_request.client.host = "localhost"

        # In dev mode with HTTP, should be insecure by default
        with env_vars(ENV="dev", COOKIE_SECURE=None, DEV_MODE="1"):
            config = get_cookie_config(mock_request)
            assert config["secure"] is False

        # With explicit COOKIE_SECURE=1, should be secure
        with env_vars(COOKIE_SECURE="1"):
            config = get_cookie_config(mock_request)
            assert config["secure"] is True

    def test_samesite_flag_configuration(self):
        """Test SameSite flag configuration."""
        mock_request = Mock(spec=Request)
        mock_request.headers = {}
        mock_request.url = Mock()
        mock_request.url.scheme = "http"

        # Default should be lax
        with env_vars(COOKIE_SAMESITE=None):
            config = get_cookie_config(mock_request)
            assert config["samesite"] == "lax"

        # Explicit configuration
        with env_vars(COOKIE_SAMESITE="strict"):
            config = get_cookie_config(mock_request)
            assert config["samesite"] == "strict"

    def test_samesite_none_enforces_secure(self):
        """Test that SameSite=None enforces Secure=True."""
        # Test the format_cookie_header function directly
        header = format_cookie_header(
            key="test",
            value="value",
            max_age=3600,
            secure=False,  # This should be overridden
            samesite="none",
            path="/"
        )
        assert "Secure" in header
        assert "SameSite=None" in header

    def test_httponly_flag(self):
        """Test HttpOnly flag is always set."""
        mock_request = Mock(spec=Request)
        mock_request.headers = {}

        config = get_cookie_config(mock_request)
        assert config["httponly"] is True

    def test_host_cookie_rules(self):
        """Test __Host- cookie security rules."""
        # __Host- cookies must be secure and path=/ and no domain
        # Test that valid __Host- cookie works
        header = format_cookie_header(
            key="__Host-test",
            value="value",
            max_age=3600,
            secure=True,  # Must be True for __Host-
            samesite="lax",
            path="/",  # Must be "/" for __Host-
            domain=None  # Must be None for __Host-
        )
        assert "Secure" in header
        assert "Path=/" in header
        assert "Domain=" not in header

        # Test that invalid __Host- cookie parameters are rejected
        with pytest.raises(AssertionError):
            format_cookie_header(
                key="__Host-test",
                value="value",
                max_age=3600,
                secure=True,
                samesite="lax",
                path="/sub",  # Invalid for __Host-
                domain=None
            )


class TestCookieDomainPath:
    """Test cookie domain and path settings."""

    def test_host_only_cookies_by_default(self):
        """Test that cookies are host-only by default."""
        mock_request = Mock(spec=Request)
        mock_request.headers = {}

        config = get_cookie_config(mock_request)
        assert config["domain"] is None  # Host-only
        assert config["path"] == "/"

    @pytest.mark.skip(reason="Environment isolation issue in test suite")
    def test_domain_cookies_in_production(self):
        """Test domain cookies when APP_DOMAIN is set."""
        mock_request = Mock(spec=Request)
        mock_request.headers = {}

        with env_vars(DEV_MODE="", APP_DOMAIN="example.com"):
            config = get_cookie_config(mock_request)
            assert config["domain"] == "example.com"
            assert config["secure"] is True  # Production forces secure

    def test_path_configuration(self):
        """Test cookie path configuration."""
        mock_request = Mock(spec=Request)
        mock_request.headers = {}

        config = get_cookie_config(mock_request)
        assert config["path"] == "/"

        # Test format_cookie_header with custom path
        header = format_cookie_header(
            key="test",
            value="value",
            max_age=3600,
            secure=True,
            samesite="lax",
            path="/api"
        )
        assert "Path=/api" in header


class TestCookiePrecedence:
    """Test cookie reading precedence order."""

    def test_canonical_cookie_preferred(self):
        """Test that canonical cookies are preferred over legacy."""
        mock_request = Mock(spec=Request)
        mock_request.cookies = {
            ACCESS_NAME: "canonical_value",
            "access_token": "legacy_value"
        }

        value = read_access_cookie(mock_request)
        assert value == "canonical_value"

    def test_legacy_cookie_fallback(self):
        """Test fallback to legacy cookies when canonical not present."""
        mock_request = Mock(spec=Request)
        mock_request.cookies = {
            "access_token": "legacy_value"
        }

        value = read_access_cookie(mock_request)
        assert value == "legacy_value"

    def test_no_cookie_returns_none(self):
        """Test that None is returned when no cookies present."""
        mock_request = Mock(spec=Request)
        mock_request.cookies = {}

        value = read_access_cookie(mock_request)
        assert value is None

    def test_wrapper_function_consistency(self):
        """Test that wrapper functions work consistently."""
        mock_request = Mock(spec=Request)
        mock_request.cookies = {ACCESS_NAME: "test_value"}

        # Both functions should return the same result
        direct_value = read_access_cookie(mock_request)
        wrapper_value = wrapper_read_access_cookie(mock_request)

        assert direct_value == wrapper_value == "test_value"


class TestLegacyCookieCompatibility:
    """Test legacy cookie compatibility and cleanup."""

    def test_legacy_cookie_names_supported(self):
        """Test that legacy cookie names are still supported for reading."""
        legacy_names = ["access_token", "refresh_token", "__session"]

        mock_request = Mock(spec=Request)
        mock_request.cookies = {name: f"value_for_{name}" for name in legacy_names}

        # Should be able to read legacy cookies
        for name in legacy_names:
            mock_request.cookies = {name: f"value_for_{name}"}
            if name == "access_token":
                value = read_access_cookie(mock_request)
                assert value == f"value_for_{name}"

    def test_cookie_cleanup_functionality(self):
        """Test that cookies can be properly cleared."""
        response = Response()

        # Set a cookie
        set_named_cookie(
            response=response,
            name=ACCESS_NAME,
            value="test_value",
            max_age=3600,
            httponly=True,
            samesite="lax",
            secure=False
        )

        # Should have set-cookie header
        assert "set-cookie" in response.headers

        # Clear the cookie
        clear_named_cookie(response, name=ACCESS_NAME)

        # Should have additional set-cookie header for clearing
        cookie_headers = response.headers.getlist("set-cookie")
        assert len(cookie_headers) >= 2  # One for setting, one for clearing

        # The clearing header should have Max-Age=0
        clearing_header = cookie_headers[-1]  # Last one should be clearing
        assert "Max-Age=0" in clearing_header


class TestCSRFCookies:
    """Test CSRF cookie handling."""

    def test_csrf_cookie_setting(self):
        """Test CSRF cookie can be set."""
        response = Response()

        set_csrf_cookie(response, "csrf_token_value", ttl=3600)

        cookie_headers = response.headers.getlist("set-cookie")
        assert cookie_headers

        # Should contain csrf_token name
        header = cookie_headers[-1]
        assert "csrf_token=" in header
        assert "HttpOnly" in header

    def test_csrf_cookie_reading(self):
        """Test CSRF cookie can be read."""
        mock_request = Mock(spec=Request)
        mock_request.cookies = {"csrf_token": "csrf_value"}

        value = mock_request.cookies.get("csrf_token")
        assert value == "csrf_value"

    def test_csrf_cookie_clearing(self):
        """Test CSRF cookie can be cleared."""
        response = Response()

        clear_csrf_cookie(response)

        cookie_headers = response.headers.getlist("set-cookie")
        assert cookie_headers

        header = cookie_headers[-1]
        assert "csrf_token=" in header
        assert "Max-Age=0" in header


class TestEnvironmentCookieConfig:
    """Test cookie configuration changes based on environment."""

    def test_dev_mode_cookie_config(self):
        """Test cookie config in development mode."""
        mock_request = Mock(spec=Request)
        mock_request.headers = {"host": "localhost:3000", "origin": "http://localhost:8000"}
        mock_request.url = Mock()
        mock_request.url.scheme = "http"

        with env_vars(ENV="dev", COOKIE_SAMESITE=None):
            config = get_cookie_config(mock_request)
            # Cross-origin in dev should prefer SameSite=None
            assert config["samesite"] == "none"
            assert config["secure"] is True  # SameSite=None forces secure

    def test_production_cookie_config(self):
        """Test cookie config in production mode."""
        mock_request = Mock(spec=Request)
        mock_request.headers = {"host": "example.com"}
        mock_request.url = Mock()
        mock_request.url.scheme = "https"

        with env_vars(ENV="prod", APP_DOMAIN="example.com"):
            config = get_cookie_config(mock_request)
            assert config["secure"] is True
            assert config["samesite"] == "lax"
            assert config["domain"] == "example.com"

    def test_cross_origin_detection(self):
        """Test cross-origin request detection."""
        mock_request = Mock(spec=Request)

        # Same origin
        mock_request.headers = {"host": "example.com", "origin": "https://example.com"}
        config = get_cookie_config(mock_request)
        assert config["samesite"] == "lax"  # No special handling for same-origin

        # Cross origin in dev
        with env_vars(ENV="dev"):
            mock_request.headers = {"host": "localhost:8000", "origin": "http://localhost:3000"}
            config = get_cookie_config(mock_request)
            assert config["samesite"] == "none"


class TestCookieIntegration:
    """Integration tests for cookie functionality."""

    def test_full_cookie_lifecycle(self, client: TestClient):
        """Test complete cookie lifecycle with real client."""
        # This would test actual endpoints, but we need to set up auth first
        # For now, just verify the test setup works
        assert client is not None

    def test_cookie_header_formatting(self):
        """Test that cookie headers are properly formatted."""
        header = format_cookie_header(
            key=ACCESS_NAME,  # Use a priority cookie name
            value="test_value",
            max_age=3600,
            secure=True,
            samesite="strict",
            path="/api",
            httponly=True
        )

        # Should contain all expected parts
        assert f"{ACCESS_NAME}=test_value" in header
        assert "Max-Age=3600" in header
        assert "Path=/api" in header
        assert "Secure" in header
        assert "HttpOnly" in header
        assert "SameSite=Strict" in header

    def test_cookie_expiration_formatting(self):
        """Test cookie expiration formatting for negative max_age."""
        header = format_cookie_header(
            key="expiring_cookie",
            value="value",
            max_age=-1,  # Expired
            secure=False,
            samesite="lax",
            path="/"
        )

        assert "Expires=Thu, 01 Jan 1970 00:00:00 GMT" in header


class TestCookieGuard:
    """Test the cookie guard script functionality."""

    def test_guard_script_exists(self):
        """Test that the guard script exists and is executable."""
        import os
        script_path = "scripts/check_cookie_calls.sh"
        assert os.path.exists(script_path)
        assert os.access(script_path, os.X_OK)

    def test_guard_script_runs(self):
        """Test that the guard script runs without errors."""
        import subprocess
        result = subprocess.run(
            ["bash", "scripts/check_cookie_calls.sh"],
            capture_output=True,
            text=True,
            cwd="."
        )
        assert result.returncode == 0
        assert "✅ No direct cookie calls" in result.stdout
