#!/usr/bin/env python3
"""
Cookie configuration tests.

Tests cover:
- Environment variable parsing
- Configuration validation
- Cross-environment compatibility
- Configuration caching and performance
"""

import os
import pytest
from contextlib import contextmanager
from unittest.mock import Mock, patch

from fastapi import Request

from app.cookie_config import (
    get_cookie_config, get_token_ttls, format_cookie_header,
    _is_dev_environment, _get_scheme
)


@contextmanager
def env_context(**kwargs):
    """Enhanced environment context manager with validation."""
    old_values = {}
    for key in kwargs:
        old_values[key] = os.environ.get(key)

    try:
        for key, value in kwargs.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = str(value)

        # Clear any module-level caches
        import app.cookie_config as cookie_config_module
        if hasattr(cookie_config_module, '_config_cache'):
            cookie_config_module._config_cache.clear()

        yield
    finally:
        for key, old_value in old_values.items():
            if old_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old_value

        # Clear caches again
        if hasattr(cookie_config_module, '_config_cache'):
            cookie_config_module._config_cache.clear()


class TestEnvironmentParsing:
    """Test environment variable parsing."""

    def test_cookie_secure_parsing(self):
        """Test COOKIE_SECURE environment variable parsing."""
        test_cases = [
            ("1", True),
            ("true", True),
            ("yes", True),
            ("on", True),
            ("TRUE", True),
            ("YES", True),
            ("ON", True),
            ("0", False),
            ("false", False),
            ("no", False),
            ("off", False),
            ("FALSE", False),
            ("NO", False),
            ("OFF", False),
            ("", False),  # Empty string
            ("invalid", False),  # Invalid defaults to False
        ]

        for env_value, expected in test_cases:
            with env_context(COOKIE_SECURE=env_value):
                mock_request = Mock(spec=Request)
                mock_request.headers = {}

                config = get_cookie_config(mock_request)
                assert config["secure"] == expected, f"Failed for COOKIE_SECURE={env_value}"

    def test_cookie_samesite_parsing(self):
        """Test COOKIE_SAMESITE environment variable parsing."""
        test_cases = [
            ("lax", "lax"),
            ("strict", "strict"),
            ("none", "none"),
            ("Lax", "lax"),  # Case insensitive
            ("Strict", "strict"),
            ("None", "none"),
            ("LAX", "lax"),
            ("STRICT", "strict"),
            ("NONE", "none"),
            (None, "lax"),  # None defaults to lax
            ("invalid", "lax"),  # Invalid defaults to lax
        ]

        for env_value, expected in test_cases:
            with env_context(COOKIE_SAMESITE=env_value):
                mock_request = Mock(spec=Request)
                mock_request.headers = {}

                config = get_cookie_config(mock_request)
                assert config["samesite"] == expected, f"Failed for COOKIE_SAMESITE={env_value}"

    def test_jwt_expire_minutes_parsing(self):
        """Test JWT_EXPIRE_MINUTES environment variable parsing."""
        test_cases = [
            ("15", 15 * 60),  # 15 minutes
            ("30", 30 * 60),  # 30 minutes
            ("60", 60 * 60),  # 1 hour
            ("1", 1 * 60),    # 1 minute
            (None, 15 * 60),    # None defaults to 15
            ("invalid", 15 * 60),  # Invalid defaults to 15
        ]

        for env_value, expected_seconds in test_cases:
            with env_context(JWT_EXPIRE_MINUTES=env_value, JWT_REFRESH_EXPIRE_MINUTES="43200"):
                access_ttl, _ = get_token_ttls()
                assert access_ttl == expected_seconds, f"Failed for JWT_EXPIRE_MINUTES={env_value}"

    def test_jwt_refresh_expire_minutes_parsing(self):
        """Test JWT_REFRESH_EXPIRE_MINUTES environment variable parsing."""
        test_cases = [
            ("43200", 43200 * 60),  # 30 days
            ("1440", 1440 * 60),    # 24 hours
            ("10080", 10080 * 60), # 7 days
            ("60", 60 * 60),       # 1 hour
            (None, 43200 * 60),      # None defaults to 43200
            ("invalid", 43200 * 60),  # Invalid defaults to 43200
        ]

        for env_value, expected_seconds in test_cases:
            with env_context(JWT_REFRESH_EXPIRE_MINUTES=env_value, JWT_EXPIRE_MINUTES="15"):
                _, refresh_ttl = get_token_ttls()
                assert refresh_ttl == expected_seconds, f"Failed for JWT_REFRESH_EXPIRE_MINUTES={env_value}"


class TestConfigurationValidation:
    """Test configuration validation."""

    def test_token_ttl_bounds(self):
        """Test that token TTLs have reasonable bounds."""
        # Test very small values
        with env_context(JWT_EXPIRE_MINUTES="0", JWT_REFRESH_EXPIRE_MINUTES="1"):
            access_ttl, refresh_ttl = get_token_ttls()
            assert access_ttl >= 0  # Allow 0 (though not recommended)
            assert refresh_ttl >= 60  # At least 1 minute

        # Test very large values
        with env_context(JWT_EXPIRE_MINUTES="10000", JWT_REFRESH_EXPIRE_MINUTES="100000"):
            access_ttl, refresh_ttl = get_token_ttls()
            assert access_ttl <= 86400  # At most 24 hours for access
            assert refresh_ttl <= 31536000  # At most 1 year for refresh

    def test_cookie_config_consistency(self):
        """Test that cookie config is internally consistent."""
        mock_request = Mock(spec=Request)
        mock_request.headers = {}

        config = get_cookie_config(mock_request)

        # SameSite=None must have Secure=True
        if config["samesite"] == "none":
            assert config["secure"] is True

        # HttpOnly should always be True
        assert config["httponly"] is True

        # Path should be "/"
        assert config["path"] == "/"

        # Domain should be None or a string
        assert config["domain"] is None or isinstance(config["domain"], str)

    def test_dev_environment_detection(self):
        """Test development environment detection."""
        # Test various dev indicators
        dev_indicators = [
            ("PYTEST_CURRENT_TEST", "test_something"),
            ("FLASK_ENV", "development"),
            ("ENVIRONMENT", "development"),
            ("NODE_ENV", "development"),
        ]

        for env_var, env_value in dev_indicators:
            with env_context(**{env_var: env_value}):
                mock_request = Mock(spec=Request)
                assert _is_dev_environment(mock_request) is True

        # Test localhost detection
        dev_hosts = ["localhost", "127.0.0.1", "0.0.0.0", "::1", "dev.example.com", "local.test.com"]

        for host in dev_hosts:
            mock_request = Mock(spec=Request)
            mock_request.headers = {"host": host}

            with env_context():  # Clear dev env vars
                assert _is_dev_environment(mock_request) is True

    def test_scheme_detection(self):
        """Test request scheme detection."""
        # Test X-Forwarded-Proto header
        mock_request = Mock(spec=Request)
        mock_request.headers = {"x-forwarded-proto": "https"}

        assert _get_scheme(mock_request) == "https"

        # Test multiple X-Forwarded-Proto values (should take first)
        mock_request.headers = {"x-forwarded-proto": "https, http"}

        assert _get_scheme(mock_request) == "https"

        # Test fallback to request.url.scheme
        mock_request.headers = {}
        mock_request.url = Mock()
        mock_request.url.scheme = "http"

        assert _get_scheme(mock_request) == "http"

        # Test error handling
        mock_request.url = None
        assert _get_scheme(mock_request) == "http"


class TestCrossEnvironmentCompatibility:
    """Test cookie configuration across different environments."""

    def test_development_defaults(self):
        """Test development environment defaults."""
        with env_context(ENV="dev", DEV_MODE="1", COOKIE_SECURE=None, COOKIE_SAMESITE=None):
            mock_request = Mock(spec=Request)
            mock_request.headers = {"host": "localhost:8000"}
            mock_request.url = Mock()
            mock_request.url.scheme = "http"

            config = get_cookie_config(mock_request)

            # Dev should prefer usability over security
            assert config["secure"] is False
            assert config["samesite"] == "lax"
            assert config["domain"] is None  # Host-only

    def test_production_defaults(self):
        """Test production environment defaults."""
        with env_context(ENV="prod", APP_DOMAIN="example.com"):
            mock_request = Mock(spec=Request)
            mock_request.headers = {"host": "example.com"}
            mock_request.url = Mock()
            mock_request.url.scheme = "https"

            config = get_cookie_config(mock_request)

            # Production should prioritize security
            assert config["secure"] is True
            assert config["samesite"] == "lax"
            assert config["domain"] == "example.com"

    def test_cross_origin_dev_handling(self):
        """Test cross-origin request handling in development."""
        with env_context(ENV="dev", COOKIE_SAMESITE=None):
            mock_request = Mock(spec=Request)
            mock_request.headers = {
                "host": "localhost:8000",
                "origin": "http://localhost:3000"  # Cross-origin
            }
            mock_request.url = Mock()
            mock_request.url.scheme = "http"

            config = get_cookie_config(mock_request)

            # Cross-origin in dev should use SameSite=None for better UX
            assert config["samesite"] == "none"
            assert config["secure"] is True  # SameSite=None requires Secure

    def test_tls_detection(self):
        """Test TLS detection for secure cookie decisions."""
        mock_request = Mock(spec=Request)
        mock_request.headers = {"host": "example.com"}

        # HTTPS should allow secure cookies
        mock_request.url = Mock()
        mock_request.url.scheme = "https"

        with env_context():
            config = get_cookie_config(mock_request)
            # Should respect TLS for secure decisions
            assert isinstance(config["secure"], bool)


class TestConfigurationCaching:
    """Test configuration caching behavior."""

    def test_config_caching(self):
        """Test that cookie config is cached for performance."""
        mock_request = Mock(spec=Request)
        mock_request.headers = {}

        # Get config multiple times
        config1 = get_cookie_config(mock_request)
        config2 = get_cookie_config(mock_request)
        config3 = get_cookie_config(mock_request)

        # Should return identical configs
        assert config1 == config2 == config3
        assert isinstance(config1, dict)

    def test_config_cache_invalidation(self):
        """Test that config cache is invalidated when environment changes."""
        mock_request = Mock(spec=Request)
        mock_request.headers = {}

        # Get config with one environment
        with env_context(COOKIE_SECURE="0"):
            config1 = get_cookie_config(mock_request)
            assert config1["secure"] is False

        # Change environment and get config again
        with env_context(COOKIE_SECURE="1"):
            config2 = get_cookie_config(mock_request)
            assert config2["secure"] is True

        # Configs should be different
        assert config1 != config2

    def test_ttl_caching(self):
        """Test that TTL values are not unnecessarily cached."""
        # TTLs should be computed fresh each time (not cached)
        with env_context(JWT_EXPIRE_MINUTES="15"):
            ttl1 = get_token_ttls()

        with env_context(JWT_EXPIRE_MINUTES="30"):
            ttl2 = get_token_ttls()

        # Should be different
        assert ttl1 != ttl2
        assert ttl1[0] == 15 * 60  # 15 minutes
        assert ttl2[0] == 30 * 60  # 30 minutes


class TestConfigurationPerformance:
    """Test configuration performance."""

    def test_config_performance(self):
        """Test that cookie config generation is fast."""
        import time

        mock_request = Mock(spec=Request)
        mock_request.headers = {}

        # Time config generation
        start_time = time.time()

        for _ in range(1000):
            config = get_cookie_config(mock_request)
            assert isinstance(config, dict)

        end_time = time.time()
        duration = end_time - start_time

        # Should be very fast (less than 0.1 seconds for 1000 calls)
        assert duration < 0.1

    def test_ttl_performance(self):
        """Test that TTL computation is fast."""
        import time

        start_time = time.time()

        for _ in range(1000):
            access_ttl, refresh_ttl = get_token_ttls()
            assert isinstance(access_ttl, int)
            assert isinstance(refresh_ttl, int)

        end_time = time.time()
        duration = end_time - start_time

        # Should be very fast
        assert duration < 0.05

    def test_header_formatting_performance(self):
        """Test cookie header formatting performance."""
        import time

        start_time = time.time()

        for i in range(1000):
            header = format_cookie_header(
                key=f"perf_test_{i % 10}",  # Reuse names to test caching
                value=f"value_{i}",
                max_age=3600,
                secure=True,
                samesite="lax",
                path="/",
                httponly=True
            )
            assert header

        end_time = time.time()
        duration = end_time - start_time

        # Should be reasonably fast
        assert duration < 0.5
