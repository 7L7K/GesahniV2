"""
Tests for configuration check endpoint.
"""

from unittest.mock import patch

from app.api.config_check import config_check


class TestConfigCheck:
    """Test configuration check endpoint functionality."""

    def test_config_check_dev_environment(self):
        """Test config check returns correct values for dev environment."""
        with patch.dict(
            "os.environ",
                {
                    "ENV": "dev",
                    "GSNH_ENABLE_SPOTIFY": "1",
                    "GSNH_ENABLE_MUSIC": "1",
                    "APPLE_OAUTH_ENABLED": "0",
                    "DEVICE_AUTH_ENABLED": "1",
                "JWT_SECRET": "test_secret_123",
                "COOKIES_SECURE": "0",  # Dev might not need HTTPS
                "COOKIES_SAMESITE": "lax",
                "REQ_ID_ENABLED": "1",
                "OPENAI_API_KEY": "test_key",
                "HOME_ASSISTANT_TOKEN": "test_token",
                "SPOTIFY_CLIENT_ID": "test_id",
            },
            clear=True,
        ):
            result = config_check()

            assert result["env"] == "dev"
            assert result["ci"] is False
            assert result["dev_mode"] is False

            # Features
            assert result["features"]["spotify"] is True
            assert result["features"]["apple_oauth"] is False
            assert result["features"]["device_auth"] is True
            assert result["features"]["preflight"] is True

            # Security
            assert result["security"]["jwt_len"] == 15  # len("test_secret_123")
            assert result["security"]["cookies_secure"] is False
            assert result["security"]["cookies_samesite"] == "lax"

            # External services
            assert result["external"]["openai_available"] is True
            assert result["external"]["home_assistant_token"] is True
            assert result["external"]["spotify_client_id"] is True

    def test_config_check_prod_environment(self):
        """Test config check returns correct values for prod environment."""
        with patch.dict(
            "os.environ",
                {
                    "ENV": "prod",
                    "CI": "0",
                    "DEV_MODE": "0",
                    "GSNH_ENABLE_SPOTIFY": "1",
                    "GSNH_ENABLE_MUSIC": "1",
                    "APPLE_OAUTH_ENABLED": "1",
                    "DEVICE_AUTH_ENABLED": "0",
                "JWT_SECRET": "a" * 64,  # Long secure secret
                "COOKIES_SECURE": "1",
                "COOKIES_SAMESITE": "strict",
                "REQ_ID_ENABLED": "1",
                "RATE_LIMIT_ENABLED": "1",
                "CORS_ENABLED": "1",
                "DETERMINISTIC_ROUTER": "1",
            },
            clear=True,
        ):
            result = config_check()

            assert result["env"] == "prod"
            assert result["ci"] is False
            assert result["dev_mode"] is False

            # Features
            assert result["features"]["spotify"] is True
            assert result["features"]["apple_oauth"] is True
            assert result["features"]["device_auth"] is False

            # Security (prod requirements)
            assert result["security"]["jwt_len"] == 64
            assert result["security"]["cookies_secure"] is True
            assert result["security"]["cookies_samesite"] == "strict"
            assert result["security"]["rate_limit_enabled"] is True
            assert result["security"]["req_id_enabled"] is True

            # Middleware
            assert result["middleware"]["cors_enabled"] is True
            assert result["middleware"]["deterministic_router"] is True

    def test_config_check_ci_environment(self):
        """Test config check returns correct values for CI environment."""
        with patch.dict(
            "os.environ",
                {
                    "ENV": "ci",
                    "CI": "1",
                    "GSNH_ENABLE_SPOTIFY": "1",  # Configured but router will disable in CI
                    "GSNH_ENABLE_MUSIC": "1",
                    "APPLE_OAUTH_ENABLED": "0",
                "JWT_SECRET": "ci_secret",
                "COOKIES_SECURE": "1",
                "COOKIES_SAMESITE": "strict",
            },
            clear=True,
        ):
            result = config_check()

            assert result["env"] == "ci"
            assert result["ci"] is True
            assert result["dev_mode"] is False

            # Features show configured values (router disables in CI, but config shows what's set)
            assert (
                result["features"]["spotify"] is True
            )  # Configured value, router handles CI disabling
            assert result["features"]["apple_oauth"] is False

            # Security
            assert result["security"]["jwt_len"] == 9  # len("ci_secret")

    def test_config_check_dev_mode_bypass(self):
        """Test that dev mode bypass shows relaxed settings."""
        with patch.dict(
            "os.environ",
            {
                "ENV": "prod",
                "DEV_MODE": "1",  # Dev mode enabled
                "JWT_SECRET": "weak",  # Would be rejected in strict prod
                "COOKIES_SECURE": "0",  # Would be rejected in strict prod
                "COOKIES_SAMESITE": "lax",  # Would be rejected in strict prod
                "REQ_ID_ENABLED": "0",  # Would be rejected in strict prod
            },
            clear=True,
        ):
            result = config_check()

            assert result["env"] == "prod"
            assert result["dev_mode"] is True

            # Security (dev mode allows relaxed settings)
            assert result["security"]["jwt_len"] == 4  # len("weak")
            assert result["security"]["cookies_secure"] is False
            assert result["security"]["cookies_samesite"] == "lax"
            assert result["security"]["req_id_enabled"] is False

    def test_config_check_missing_values(self):
        """Test config check handles missing environment variables."""
        with patch.dict("os.environ", {}, clear=True):
            result = config_check()

            assert result["env"] == "dev"  # Default
            assert result["ci"] is False
            assert result["dev_mode"] is False

            # Features default to False/True as appropriate
            assert result["features"]["spotify"] is False
            assert result["features"]["apple_oauth"] is False
            assert result["features"]["device_auth"] is False
            assert result["features"]["preflight"] is True  # Default is "1"

            # Security defaults
            assert result["security"]["jwt_len"] == 0  # Empty string
            assert result["security"]["cookies_secure"] is True  # Default "1"
            assert result["security"]["cookies_samesite"] == "strict"  # Default
            assert result["security"]["rate_limit_enabled"] is True  # Default "1"
            assert result["security"]["req_id_enabled"] is True  # Default "1"

            # External services
            assert result["external"]["openai_available"] is False
            assert result["external"]["home_assistant_token"] is False
            assert result["external"]["spotify_client_id"] is False
