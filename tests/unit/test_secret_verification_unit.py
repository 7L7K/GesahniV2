"""
Unit tests for secret verification functionality.
"""

import os
from unittest.mock import patch

from app.secret_verification import (
    CRITICAL_SECRETS,
    get_insecure_secrets,
    get_missing_required_secrets,
    log_secret_summary,
    verify_secrets_on_boot,
)


class TestSecretVerification:
    """Test secret verification functionality."""

    def test_verify_secrets_on_boot_all_set(self):
        """Test verification when all required secrets are properly set."""
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET": "a-very-long-and-secure-jwt-secret-key-that-is-at-least-64-characters-long",
                "OPENAI_API_KEY": "sk-proj-1234567890abcdef",
                "HOME_ASSISTANT_TOKEN": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9",
                "GOOGLE_CLIENT_SECRET": "GOCSPX-secret123",
            },
        ):
            results = verify_secrets_on_boot()

            assert results["JWT_SECRET"]["status"] == "SET_SECURE"
            assert results["OPENAI_API_KEY"]["status"] == "SET_SECURE"
            assert results["HOME_ASSISTANT_TOKEN"]["status"] == "SET_SECURE"
            assert results["GOOGLE_CLIENT_SECRET"]["status"] == "SET_SECURE"

    def test_verify_secrets_on_boot_missing_required(self):
        """Test verification when required secrets are missing."""
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET": "",
                "OPENAI_API_KEY": "",
                "HOME_ASSISTANT_TOKEN": "optional-token",
            },
            clear=True,
        ):
            results = verify_secrets_on_boot()

            assert results["JWT_SECRET"]["status"] == "MISSING_REQUIRED"
            assert results["OPENAI_API_KEY"]["status"] == "MISSING_REQUIRED"
            assert results["HOME_ASSISTANT_TOKEN"]["status"] == "SET_SECURE"

    def test_verify_secrets_on_boot_insecure_defaults(self):
        """Test verification detects insecure default values."""
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET": "secret",
                "OPENAI_API_KEY": "sk-test-1234567890abcdef",
                "HOME_ASSISTANT_TOKEN": "change-me",
            },
        ):
            results = verify_secrets_on_boot()

            assert results["JWT_SECRET"]["status"] == "INSECURE_DEFAULT"
            assert results["OPENAI_API_KEY"]["status"] == "TEST_KEY"
            assert results["HOME_ASSISTANT_TOKEN"]["status"] == "SET_SECURE"

    def test_verify_secrets_on_boot_weak_jwt_secret(self):
        """Test verification detects weak JWT secrets."""
        with patch.dict(
            os.environ,
            {"JWT_SECRET": "short", "OPENAI_API_KEY": "sk-proj-1234567890abcdef"},
        ):
            results = verify_secrets_on_boot()

            assert results["JWT_SECRET"]["status"] == "WEAK_SECRET"
            assert results["OPENAI_API_KEY"]["status"] == "SET_SECURE"

    def test_verify_secrets_on_boot_invalid_openai_format(self):
        """Test verification detects invalid OpenAI API key format."""
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET": "a-very-long-and-secure-jwt-secret-key-that-is-at-least-64-characters-long",
                "OPENAI_API_KEY": "invalid-format-key",
            },
        ):
            results = verify_secrets_on_boot()

            assert results["JWT_SECRET"]["status"] == "SET_SECURE"
            assert results["OPENAI_API_KEY"]["status"] == "INVALID_FORMAT"

    def test_get_missing_required_secrets(self):
        """Test getting list of missing required secrets."""
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET": "",
                "OPENAI_API_KEY": "",
                "HOME_ASSISTANT_TOKEN": "optional-token",
            },
            clear=True,
        ):
            missing = get_missing_required_secrets()

            assert "JWT_SECRET" in missing
            assert "OPENAI_API_KEY" in missing
            assert "HOME_ASSISTANT_TOKEN" not in missing

    def test_get_insecure_secrets(self):
        """Test getting list of insecure secrets."""
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET": "secret",
                "OPENAI_API_KEY": "sk-test-1234567890abcdef",
                "HOME_ASSISTANT_TOKEN": "a-very-long-and-secure-jwt-secret-key-that-is-at-least-64-characters-long",
            },
        ):
            insecure = get_insecure_secrets()

            assert "JWT_SECRET" in insecure
            assert "OPENAI_API_KEY" in insecure
            assert "HOME_ASSISTANT_TOKEN" not in insecure

    def test_log_secret_summary_all_good(self, caplog):
        """Test secret summary logging when all secrets are properly configured."""
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET": "a-very-long-and-secure-jwt-secret-key-that-is-at-least-64-characters-long",
                "OPENAI_API_KEY": "sk-proj-1234567890abcdef",
            },
        ):
            log_secret_summary()

            assert "All critical secrets are properly configured" in caplog.text

    def test_log_secret_summary_missing_required(self, caplog):
        """Test secret summary logging when required secrets are missing."""
        with patch.dict(
            os.environ, {"JWT_SECRET": "", "OPENAI_API_KEY": ""}, clear=True
        ):
            log_secret_summary()

            assert "Missing required secrets" in caplog.text
            assert "JWT_SECRET" in caplog.text
            assert "OPENAI_API_KEY" in caplog.text

    def test_log_secret_summary_insecure_secrets(self, caplog):
        """Test secret summary logging when secrets are insecure."""
        with patch.dict(
            os.environ,
            {"JWT_SECRET": "secret", "OPENAI_API_KEY": "sk-test-1234567890abcdef"},
        ):
            log_secret_summary()

            assert "Secrets with security issues" in caplog.text
            assert "JWT_SECRET" in caplog.text
            assert "OPENAI_API_KEY" in caplog.text

    def test_critical_secrets_configuration(self):
        """Test that CRITICAL_SECRETS configuration is properly structured."""
        for secret_name, config in CRITICAL_SECRETS.items():
            assert "description" in config
            assert "required" in config
            assert "insecure_defaults" in config
            assert isinstance(config["description"], str)
            assert isinstance(config["required"], bool)
            assert isinstance(config["insecure_defaults"], set)

    def test_verify_secrets_on_boot_optional_secrets_not_set(self):
        """Test verification handles optional secrets that are not set."""
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET": "a-very-long-and-secure-jwt-secret-key-that-is-at-least-64-characters-long",
                "OPENAI_API_KEY": "sk-proj-1234567890abcdef",
            },
            clear=True,
        ):
            results = verify_secrets_on_boot()

            # Required secrets should be set
            assert results["JWT_SECRET"]["status"] == "SET_SECURE"
            assert results["OPENAI_API_KEY"]["status"] == "SET_SECURE"

            # Optional secrets should be marked as missing but not required
            assert results["HOME_ASSISTANT_TOKEN"]["status"] == "MISSING_OPTIONAL"
            assert results["GOOGLE_CLIENT_SECRET"]["status"] == "MISSING_OPTIONAL"
            assert not results["HOME_ASSISTANT_TOKEN"]["required"]
            assert not results["GOOGLE_CLIENT_SECRET"]["required"]
