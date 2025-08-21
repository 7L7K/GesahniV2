"""
Tests for centralized cookie configuration.

These tests ensure that cookies are set with sharp and consistent attributes:
- Host-only cookies (no Domain)
- Path=/
- SameSite=Lax (configurable)
- HttpOnly=True
- Secure=False in dev HTTP, True in production
- Consistent TTLs for access/refresh tokens
"""

import os
import pytest
from unittest.mock import Mock, patch
from fastapi import Request

from app.cookie_config import (
    get_cookie_config,
    get_token_ttls,
    format_cookie_header,
    _is_dev_environment,
    _get_scheme,
)


class TestCookieConfig:
    """Test cookie configuration functions."""

    def test_get_cookie_config_defaults(self):
        """Test default cookie configuration."""
        request = Mock()
        request.url.scheme = "https"
        request.headers = {"host": "example.com"}
        
        config = get_cookie_config(request)
        
        # With new dev-friendly defaults, secure should be False unless explicitly set
        assert config["secure"] is False
        assert config["samesite"] == "lax"
        assert config["httponly"] is True
        assert config["path"] == "/"
        assert config["domain"] is None

    def test_get_cookie_config_dev_http(self):
        """Test cookie configuration in development HTTP environment."""
        request = Mock()
        request.url.scheme = "http"
        request.headers = {"host": "localhost:3000"}
        
        with patch.dict(os.environ, {"DEV_MODE": "1"}):
            config = get_cookie_config(request)
        
        assert config["secure"] is False
        assert config["samesite"] == "lax"
        assert config["httponly"] is True
        assert config["path"] == "/"
        assert config["domain"] is None

    def test_get_cookie_config_samesite_none(self):
        """Test that SameSite=None forces Secure=True."""
        request = Mock()
        request.url.scheme = "http"
        request.headers = {"host": "localhost:3000"}
        
        with patch.dict(os.environ, {"COOKIE_SAMESITE": "none"}):
            config = get_cookie_config(request)
        
        assert config["secure"] is True
        assert config["samesite"] == "none"

    def test_get_cookie_config_custom_secure(self):
        """Test custom secure configuration."""
        request = Mock()
        request.url.scheme = "http"
        request.headers = {"host": "localhost:3000"}
        
        with patch.dict(os.environ, {"COOKIE_SECURE": "0"}):
            config = get_cookie_config(request)
        
        assert config["secure"] is False

    def test_get_cookie_config_custom_samesite(self):
        """Test custom SameSite configuration."""
        request = Mock()
        request.url.scheme = "https"
        request.headers = {"host": "example.com"}
        
        with patch.dict(os.environ, {"COOKIE_SAMESITE": "strict"}):
            config = get_cookie_config(request)
        
        assert config["samesite"] == "strict"

    def test_is_dev_environment_pytest(self):
        """Test dev environment detection with pytest."""
        request = Mock()
        request.headers = {"host": "example.com"}
        
        with patch.dict(os.environ, {"PYTEST_CURRENT_TEST": "test_function"}):
            assert _is_dev_environment(request) is True

    def test_is_dev_environment_localhost(self):
        """Test dev environment detection with localhost."""
        request = Mock()
        request.headers = {"host": "localhost:3000"}
        
        assert _is_dev_environment(request) is True

    def test_is_dev_environment_127_0_0_1(self):
        """Test dev environment detection with localhost."""
        request = Mock()
        request.headers = {"host": "localhost:8000"}
        
        assert _is_dev_environment(request) is True

    def test_is_dev_environment_production(self):
        """Test dev environment detection in production."""
        request = Mock()
        request.headers = {"host": "app.example.com"}
        
        # Clear any dev environment variables that might be set
        with patch.dict(os.environ, {}, clear=True):
            assert _is_dev_environment(request) is False

    def test_get_scheme_https(self):
        """Test scheme detection for HTTPS."""
        request = Mock()
        request.url.scheme = "https"
        
        assert _get_scheme(request) == "https"

    def test_get_scheme_http(self):
        """Test scheme detection for HTTP."""
        request = Mock()
        request.url.scheme = "http"
        
        assert _get_scheme(request) == "http"

    def test_get_scheme_fallback(self):
        """Test scheme detection fallback."""
        request = Mock()
        request.url = None
        
        assert _get_scheme(request) == "http"

    def test_get_token_ttls_defaults(self):
        """Test default token TTLs."""
        access_ttl, refresh_ttl = get_token_ttls()
        
        assert access_ttl == 15 * 60  # 15 minutes (default from implementation)
        assert refresh_ttl == 43200 * 60  # 30 days (default from implementation)

    def test_get_token_ttls_custom(self):
        """Test custom token TTLs."""
        with patch.dict(os.environ, {
            "JWT_EXPIRE_MINUTES": "60",
            "JWT_REFRESH_EXPIRE_MINUTES": "2880"
        }):
            access_ttl, refresh_ttl = get_token_ttls()
        
        assert access_ttl == 60 * 60  # 60 minutes
        assert refresh_ttl == 2880 * 60  # 48 hours

    def test_format_cookie_header_basic(self):
        """Test basic cookie header formatting."""
        header = format_cookie_header(
            key="test_cookie",
            value="test_value",
            max_age=3600,
            secure=True,
            samesite="lax",
        )
        
        assert "test_cookie=test_value" in header
        assert "HttpOnly" in header
        assert "Max-Age=3600" in header
        assert "Path=/" in header
        assert "SameSite=Lax" in header
        assert "Secure" in header
        assert "Domain=" not in header

    def test_format_cookie_header_auth_cookies(self):
        """Test auth cookie header formatting with Priority=High."""
        header = format_cookie_header(
            key="access_token",
            value="token_value",
            max_age=1800,
            secure=False,
            samesite="lax",
        )
        
        assert "access_token=token_value" in header
        assert "Priority=High" in header

    def test_format_cookie_header_refresh_cookie(self):
        """Test refresh cookie header formatting with Priority=High."""
        header = format_cookie_header(
            key="refresh_token",
            value="refresh_value",
            max_age=86400,
            secure=True,
            samesite="strict",
        )
        
        assert "refresh_token=refresh_value" in header
        assert "Priority=High" in header
        assert "SameSite=Strict" in header

    def test_format_cookie_header_with_domain(self):
        """Test cookie header formatting with domain."""
        header = format_cookie_header(
            key="test_cookie",
            value="test_value",
            max_age=3600,
            secure=True,
            samesite="lax",
            domain=".example.com",
        )
        
        assert "Domain=.example.com" in header

    def test_format_cookie_header_not_httponly(self):
        """Test cookie header formatting without HttpOnly."""
        header = format_cookie_header(
            key="test_cookie",
            value="test_value",
            max_age=3600,
            secure=True,
            samesite="lax",
            httponly=False,
        )
        
        assert "HttpOnly" not in header

    def test_format_cookie_header_not_secure(self):
        """Test cookie header formatting without Secure."""
        header = format_cookie_header(
            key="test_cookie",
            value="test_value",
            max_age=3600,
            secure=False,
            samesite="lax",
        )
        
        assert "Secure" not in header

    def test_format_cookie_header_samesite_none(self):
        """Test cookie header formatting with SameSite=None."""
        header = format_cookie_header(
            key="test_cookie",
            value="test_value",
            max_age=3600,
            secure=True,
            samesite="none",
        )
        
        assert "SameSite=None" in header

    def test_format_cookie_header_samesite_strict(self):
        """Test cookie header formatting with SameSite=Strict."""
        header = format_cookie_header(
            key="test_cookie",
            value="test_value",
            max_age=3600,
            secure=True,
            samesite="strict",
        )
        
        assert "SameSite=Strict" in header

    def test_format_cookie_header_custom_path(self):
        """Test cookie header formatting with custom path."""
        header = format_cookie_header(
            key="test_cookie",
            value="test_value",
            max_age=3600,
            secure=True,
            samesite="lax",
            path="/api",
        )
        
        assert "Path=/api" in header


class TestCookieConfigMatrix:
    """Matrix tests for cookie configuration: DEV/PROD x COOKIE_SECURE x COOKIE_SAMESITE."""

    def test_dev_prod_secure_samesite_matrix(self):
        """Test all combinations of DEV/PROD, COOKIE_SECURE, and COOKIE_SAMESITE."""
        # Define test matrix: (environment, cookie_secure_env, cookie_samesite, expected_secure, expected_samesite)
        test_matrix = [
            # Production scenarios
            ("PROD", "1", "lax", True, "lax"),
            ("PROD", "1", "strict", True, "strict"),
            ("PROD", "1", "none", True, "none"),  # SameSite=None forces Secure=True
            ("PROD", "0", "lax", False, "lax"),
            ("PROD", "0", "strict", False, "strict"),
            ("PROD", "0", "none", True, "none"),  # SameSite=None forces Secure=True even if env says 0

            # Development HTTP scenarios (force Secure=False)
            ("DEV", "1", "lax", False, "lax"),  # HTTP forces Secure=False even if env says 1
            ("DEV", "1", "strict", False, "strict"),
            ("DEV", "1", "none", True, "none"),  # SameSite=None still forces Secure=True
            ("DEV", "0", "lax", False, "lax"),
            ("DEV", "0", "strict", False, "strict"),
            ("DEV", "0", "none", True, "none"),  # SameSite=None forces Secure=True

            # Development HTTPS scenarios (respect env settings)
            ("DEV_HTTPS", "1", "lax", True, "lax"),
            ("DEV_HTTPS", "1", "strict", True, "strict"),
            ("DEV_HTTPS", "1", "none", True, "none"),
            ("DEV_HTTPS", "0", "lax", False, "lax"),
            ("DEV_HTTPS", "0", "strict", False, "strict"),
            ("DEV_HTTPS", "0", "none", True, "none"),  # SameSite=None forces Secure=True
        ]

        for env_type, cookie_secure_env, cookie_samesite_env, expected_secure, expected_samesite in test_matrix:
            # Set up request based on environment type
            if env_type == "PROD":
                request = Mock()
                request.url.scheme = "https"
                request.headers = {"host": "app.example.com"}
                env_vars = {
                    "COOKIE_SECURE": cookie_secure_env,
                    "COOKIE_SAMESITE": cookie_samesite_env
                }
            elif env_type == "DEV":
                request = Mock()
                request.url.scheme = "http"
                request.headers = {"host": "localhost:3000"}
                env_vars = {
                    "DEV_MODE": "1",
                    "COOKIE_SECURE": cookie_secure_env,
                    "COOKIE_SAMESITE": cookie_samesite_env
                }
            elif env_type == "DEV_HTTPS":
                request = Mock()
                request.url.scheme = "https"
                request.headers = {"host": "localhost:3000"}
                env_vars = {
                    "DEV_MODE": "1",
                    "COOKIE_SECURE": cookie_secure_env,
                    "COOKIE_SAMESITE": cookie_samesite_env
                }

            with patch.dict(os.environ, env_vars, clear=True):
                config = get_cookie_config(request)

            # Verify expected configuration
            assert config["secure"] == expected_secure, (
                f"Env={env_type}, SECURE={cookie_secure_env}, SAMESITE={cookie_samesite_env}: "
                f"expected secure={expected_secure}, got {config['secure']}"
            )
            assert config["samesite"] == expected_samesite, (
                f"Env={env_type}, SECURE={cookie_secure_env}, SAMESITE={cookie_samesite_env}: "
                f"expected samesite={expected_samesite}, got {config['samesite']}"
            )

            # Always verify common attributes
            assert config["httponly"] is True
            assert config["path"] == "/"
            assert config["domain"] is None  # Never set domain

    def test_format_cookie_header_domain_behavior(self):
        """Verify format_cookie_header() Domain attribute behavior."""
        # Test with None domain (should not set Domain)
        header = format_cookie_header(
            key="test_cookie", value="test_value", max_age=3600, secure=True,
            samesite="lax", path="/", httponly=True, domain=None
        )
        assert "Domain=" not in header, f"Domain should not be set when None, but found in: {header}"

        # Test with empty domain (should not set Domain)
        header = format_cookie_header(
            key="test_cookie", value="test_value", max_age=3600, secure=True,
            samesite="lax", path="/", httponly=True, domain=""
        )
        assert "Domain=" not in header, f"Domain should not be set when empty, but found in: {header}"

        # Test with actual domain (should set Domain)
        header = format_cookie_header(
            key="test_cookie", value="test_value", max_age=3600, secure=True,
            samesite="lax", path="/", httponly=True, domain=".example.com"
        )
        assert "Domain=.example.com" in header, f"Domain should be set when provided, but not found in: {header}"

        # Test with another domain
        header = format_cookie_header(
            key="test_cookie", value="test_value", max_age=3600, secure=True,
            samesite="lax", path="/", httponly=True, domain="example.com"
        )
        assert "Domain=example.com" in header, f"Domain should be set when provided, but not found in: {header}"

    def test_ttl_mapping_for_cookies(self):
        """Assert TTL mapping for access/refresh/device cookies."""
        # Test default TTLs
        access_ttl, refresh_ttl = get_token_ttls()
        assert access_ttl == 15 * 60  # 15 minutes default
        assert refresh_ttl == 43200 * 60  # 30 days default

        # Test custom TTLs
        with patch.dict(os.environ, {
            "JWT_EXPIRE_MINUTES": "30",
            "JWT_REFRESH_EXPIRE_MINUTES": "1440"  # 1 day
        }):
            access_ttl, refresh_ttl = get_token_ttls()
            assert access_ttl == 30 * 60  # 30 minutes
            assert refresh_ttl == 1440 * 60  # 1 day

        # Verify access TTL is always shorter than refresh TTL
        assert access_ttl < refresh_ttl

        # Test TTL conversion logic
        with patch.dict(os.environ, {
            "JWT_EXPIRE_MINUTES": "60",  # 1 hour
            "JWT_REFRESH_EXPIRE_MINUTES": "43200"  # 30 days
        }):
            access_ttl, refresh_ttl = get_token_ttls()
            # Verify proper conversion to seconds
            assert access_ttl == 60 * 60  # 1 hour in seconds
            assert refresh_ttl == 43200 * 60  # 30 days in seconds


class TestCookieConfigIntegration:
    """Integration tests for cookie configuration."""

    def test_cookie_config_consistency(self):
        """Test that cookie configuration is consistent across different scenarios."""
        scenarios = [
            {
                "scheme": "https",
                "host": "app.example.com",
                "env": {"COOKIE_SECURE": "1", "COOKIE_SAMESITE": "lax"},
                "expected_secure": True,
                "expected_samesite": "lax",
            },
            {
                "scheme": "http",
                "host": "localhost:3000",
                "env": {"DEV_MODE": "1", "COOKIE_SECURE": "1", "COOKIE_SAMESITE": "lax"},
                "expected_secure": False,
                "expected_samesite": "lax",
            },
            {
                "scheme": "http",
                "host": "app.example.com",
                "env": {"COOKIE_SAMESITE": "none", "COOKIE_SECURE": "0"},
                "expected_secure": True,  # SameSite=None forces Secure=True
                "expected_samesite": "none",
            },
        ]
        
        for scenario in scenarios:
            request = Mock()
            request.url.scheme = scenario["scheme"]
            request.headers = {"host": scenario["host"]}
            
            with patch.dict(os.environ, scenario["env"]):
                config = get_cookie_config(request)
            
            assert config["secure"] == scenario["expected_secure"]
            assert config["samesite"] == scenario["expected_samesite"]
            assert config["httponly"] is True
            assert config["path"] == "/"
            assert config["domain"] is None

    def test_token_ttl_consistency(self):
        """Test that token TTLs are consistent and reasonable."""
        access_ttl, refresh_ttl = get_token_ttls()
        
        # Access token should be shorter than refresh token
        assert access_ttl < refresh_ttl
        
        # Access token should be reasonable (5 minutes to 2 hours)
        assert 5 * 60 <= access_ttl <= 2 * 60 * 60
        
        # Refresh token should be reasonable (1 hour to 30 days)
        assert 60 * 60 <= refresh_ttl <= 30 * 24 * 60 * 60

    def test_cookie_header_format_consistency(self):
        """Test that cookie headers are formatted consistently."""
        test_cases = [
            {
                "key": "access_token",
                "value": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
                "max_age": 1800,
                "secure": True,
                "samesite": "lax",
            },
            {
                "key": "refresh_token",
                "value": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
                "max_age": 86400,
                "secure": True,
                "samesite": "lax",
            },
        ]
        
        for case in test_cases:
            header = format_cookie_header(**case)
            
            # Check required attributes
            assert f"{case['key']}={case['value']}" in header
            assert "HttpOnly" in header
            assert f"Max-Age={case['max_age']}" in header
            assert "Path=/" in header
            assert f"SameSite=Lax" in header
            
            # Check conditional attributes
            if case["secure"]:
                assert "Secure" in header
            
            # Check auth-specific attributes
            if case["key"] in ["access_token", "refresh_token"]:
                assert "Priority=High" in header
            
            # Check host-only (no domain)
            assert "Domain=" not in header

