"""Tests for URL helper functions."""

import os
import pytest
from unittest.mock import patch

from app.url_helpers import (
    get_app_url,
    get_frontend_url,
    build_ws_url,
    build_api_url,
    is_dev_environment
)


class TestGetAppUrl:
    """Test get_app_url function."""

    def test_get_app_url_with_explicit_app_url(self):
        """Test with explicit APP_URL environment variable."""
        with patch.dict(os.environ, {"APP_URL": "https://api.example.com"}):
            result = get_app_url()
            assert result == "https://api.example.com"

    def test_get_app_url_with_explicit_app_url_trailing_slash(self):
        """Test with explicit APP_URL that has trailing slash."""
        with patch.dict(os.environ, {"APP_URL": "https://api.example.com/"}):
            result = get_app_url()
            assert result == "https://api.example.com"

    def test_get_app_url_default_values(self):
        """Test with default host and port values."""
        with patch.dict(os.environ, {}, clear=True):
            result = get_app_url()
            assert result == "http://127.0.0.1:8000"

    def test_get_app_url_custom_host_port(self):
        """Test with custom host and port."""
        with patch.dict(os.environ, {"HOST": "0.0.0.0", "PORT": "9000"}, clear=True):
            result = get_app_url()
            assert result == "http://0.0.0.0:9000"

    def test_get_app_url_force_https(self):
        """Test with FORCE_HTTPS enabled."""
        with patch.dict(os.environ, {"FORCE_HTTPS": "1"}, clear=True):
            result = get_app_url()
            assert result == "https://127.0.0.1:8000"


class TestGetFrontendUrl:
    """Test get_frontend_url function."""

    def test_get_frontend_url_default(self):
        """Test with default CORS_ALLOW_ORIGINS."""
        with patch.dict(os.environ, {}, clear=True):
            result = get_frontend_url()
            assert result == "http://localhost:3000"

    def test_get_frontend_url_single_origin(self):
        """Test with single origin."""
        with patch.dict(os.environ, {"CORS_ALLOW_ORIGINS": "https://app.example.com"}):
            result = get_frontend_url()
            assert result == "https://app.example.com"

    def test_get_frontend_url_multiple_origins(self):
        """Test with multiple origins - should use first one."""
        with patch.dict(os.environ, {"CORS_ALLOW_ORIGINS": "https://app1.com,https://app2.com"}):
            result = get_frontend_url()
            assert result == "https://app1.com"

    def test_get_frontend_url_with_spaces(self):
        """Test with origins that have spaces."""
        with patch.dict(os.environ, {"CORS_ALLOW_ORIGINS": " https://app.com , https://other.com "}):
            result = get_frontend_url()
            assert result == "https://app.com"


class TestBuildWsUrl:
    """Test build_ws_url function."""

    def test_build_ws_url_http_to_ws(self):
        """Test converting HTTP to WebSocket."""
        result = build_ws_url("/v1/ws/care", "http://127.0.0.1:8000")
        assert result == "ws://127.0.0.1:8000/v1/ws/care"

    def test_build_ws_url_https_to_wss(self):
        """Test converting HTTPS to WSS."""
        result = build_ws_url("/v1/ws/care", "https://api.example.com")
        assert result == "wss://api.example.com/v1/ws/care"

    def test_build_ws_url_with_base_url_none(self):
        """Test with base_url=None (should use get_app_url)."""
        with patch('app.url_helpers.get_app_url', return_value="http://127.0.0.1:8000"):
            result = build_ws_url("/v1/ws/care")
            assert result == "ws://127.0.0.1:8000/v1/ws/care"

    def test_build_ws_url_with_existing_path(self):
        """Test with base URL that has existing path."""
        result = build_ws_url("/v1/ws/care", "http://127.0.0.1:8000/api")
        assert result == "ws://127.0.0.1:8000/v1/ws/care"


class TestBuildApiUrl:
    """Test build_api_url function."""

    def test_build_api_url_simple(self):
        """Test building simple API URL."""
        result = build_api_url("/v1/auth/login", "http://127.0.0.1:8000")
        assert result == "http://127.0.0.1:8000/v1/auth/login"

    def test_build_api_url_with_base_url_none(self):
        """Test with base_url=None (should use get_app_url)."""
        with patch('app.url_helpers.get_app_url', return_value="http://127.0.0.1:8000"):
            result = build_api_url("/v1/auth/login")
            assert result == "http://127.0.0.1:8000/v1/auth/login"

    def test_build_api_url_with_existing_path(self):
        """Test with base URL that has existing path."""
        result = build_api_url("/v1/auth/login", "http://127.0.0.1:8000/api")
        assert result == "http://127.0.0.1:8000/v1/auth/login"


class TestIsDevEnvironment:
    """Test is_dev_environment function."""

    def test_is_dev_environment_pytest(self):
        """Test with PYTEST_CURRENT_TEST set."""
        with patch.dict(os.environ, {"PYTEST_CURRENT_TEST": "test_something"}):
            assert is_dev_environment() is True

    def test_is_dev_environment_flask_dev(self):
        """Test with FLASK_ENV=development."""
        with patch.dict(os.environ, {"FLASK_ENV": "development"}):
            assert is_dev_environment() is True

    def test_is_dev_environment_env_dev(self):
        """Test with ENVIRONMENT=development."""
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}):
            assert is_dev_environment() is True

    def test_is_dev_environment_node_dev(self):
        """Test with NODE_ENV=development."""
        with patch.dict(os.environ, {"NODE_ENV": "development"}):
            assert is_dev_environment() is True

    def test_is_dev_environment_production(self):
        """Test in production environment."""
        with patch.dict(os.environ, {}, clear=True):
            assert is_dev_environment() is False

    def test_is_dev_environment_mixed(self):
        """Test with mixed environment variables."""
        with patch.dict(os.environ, {
            "NODE_ENV": "production",
            "FLASK_ENV": "production",
            "ENVIRONMENT": "production"
        }, clear=True):
            assert is_dev_environment() is False
