"""
Tests for production configuration guardrails.
"""
from unittest.mock import patch

import pytest

from app.startup.config_guard import ConfigError, _is_truthy, assert_strict_prod


class TestConfigGuard:
    """Test configuration guard functionality."""

    def test_is_truthy_various_values(self):
        """Test the _is_truthy helper function."""
        assert _is_truthy("1") is True
        assert _is_truthy("true") is True
        assert _is_truthy("TRUE") is True
        assert _is_truthy("yes") is True
        assert _is_truthy("on") is True
        assert _is_truthy("0") is False
        assert _is_truthy("false") is False
        assert _is_truthy("") is False
        assert _is_truthy(None) is False

    def test_skip_in_dev_mode(self):
        """Test that guardrails are skipped in dev mode."""
        with patch.dict("os.environ", {"ENV": "prod", "DEV_MODE": "1"}, clear=True):
            # Should not raise any exception
            assert_strict_prod()

    def test_skip_in_non_prod_env(self):
        """Test that guardrails are skipped in non-prod environments."""
        for env in ["dev", "ci", "staging"]:
            with patch.dict("os.environ", {"ENV": env}, clear=True):
                # Should not raise any exception
                assert_strict_prod()

    def test_jwt_secret_too_short_in_prod(self):
        """Test that weak JWT secret is rejected in prod."""
        with patch.dict("os.environ", {
            "ENV": "prod",
            "JWT_SECRET": "short",  # Only 5 chars, needs >=32
            "COOKIES_SECURE": "1",
            "COOKIES_SAMESITE": "strict",
            "REQ_ID_ENABLED": "1"
        }, clear=True):
            with pytest.raises(ConfigError, match="JWT_SECRET too weak"):
                assert_strict_prod()

    def test_jwt_secret_valid_in_prod(self):
        """Test that valid JWT secret is accepted in prod."""
        with patch.dict("os.environ", {
            "ENV": "prod",
            "JWT_SECRET": "a" * 32,  # 32 chars, valid
            "COOKIES_SECURE": "1",
            "COOKIES_SAMESITE": "strict",
            "REQ_ID_ENABLED": "1"
        }, clear=True):
            # Should not raise any exception
            assert_strict_prod()

    def test_cookies_insecure_in_prod(self):
        """Test that insecure cookies are rejected in prod."""
        with patch.dict("os.environ", {
            "ENV": "prod",
            "JWT_SECRET": "a" * 32,
            "COOKIES_SECURE": "0",  # Insecure!
            "COOKIES_SAMESITE": "strict",
            "REQ_ID_ENABLED": "1"
        }, clear=True):
            with pytest.raises(ConfigError, match="COOKIES_SECURE must be enabled"):
                assert_strict_prod()

    def test_cookies_weak_samesite_in_prod(self):
        """Test that weak SameSite is rejected in prod."""
        with patch.dict("os.environ", {
            "ENV": "prod",
            "JWT_SECRET": "a" * 32,
            "COOKIES_SECURE": "1",
            "COOKIES_SAMESITE": "lax",  # Not strict!
            "REQ_ID_ENABLED": "1"
        }, clear=True):
            with pytest.raises(ConfigError, match="COOKIES_SAMESITE must be 'strict'"):
                assert_strict_prod()

    def test_request_id_disabled_in_prod(self):
        """Test that disabled request IDs are rejected in prod."""
        with patch.dict("os.environ", {
            "ENV": "prod",
            "JWT_SECRET": "a" * 32,
            "COOKIES_SECURE": "1",
            "COOKIES_SAMESITE": "strict",
            "REQ_ID_ENABLED": "0"  # Disabled!
        }, clear=True):
            with pytest.raises(ConfigError, match="REQ_ID_ENABLED must be on"):
                assert_strict_prod()

    def test_valid_prod_config_passes(self):
        """Test that a valid production config passes all checks."""
        with patch.dict("os.environ", {
            "ENV": "prod",
            "JWT_SECRET": "a" * 32,
            "COOKIES_SECURE": "1",
            "COOKIES_SAMESITE": "strict",
            "REQ_ID_ENABLED": "1",
            "SPOTIFY_ENABLED": "1",  # Optional, but explicitly enabled
        }, clear=True):
            # Should not raise any exception
            assert_strict_prod()

    def test_production_env_variants(self):
        """Test that both 'prod' and 'production' trigger strict checks."""
        for prod_env in ["prod", "production"]:
            with patch.dict("os.environ", {
                "ENV": prod_env,
                "JWT_SECRET": "a" * 32,
                "COOKIES_SECURE": "1",
                "COOKIES_SAMESITE": "strict",
                "REQ_ID_ENABLED": "1"
            }, clear=True):
                # Should not raise any exception (valid config)
                assert_strict_prod()
