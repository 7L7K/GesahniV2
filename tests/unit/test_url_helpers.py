"""Tests for URL helper functions."""

import os
import pytest
from unittest.mock import patch, Mock
from fastapi import Request

from app.url_helpers import (
    get_app_url,
    get_frontend_url,
    build_ws_url,
    build_api_url,
    is_dev_environment,
    build_origin_aware_url,
    sanitize_redirect_path,
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
            assert result == "http://localhost:8000"

    def test_get_app_url_custom_host_port(self):
        """Test with custom host and port."""
        with patch.dict(os.environ, {"HOST": "0.0.0.0", "PORT": "9000"}, clear=True):
            result = get_app_url()
            assert result == "http://0.0.0.0:9000"

    def test_get_app_url_force_https(self):
        """Test with FORCE_HTTPS enabled."""
        with patch.dict(os.environ, {"FORCE_HTTPS": "1"}, clear=True):
            result = get_app_url()
            assert result == "https://localhost:8000"

    def test_get_app_url_force_https_various_values(self):
        """Test with various FORCE_HTTPS values."""
        for value in ["true", "yes", "on", "TRUE", "YES", "ON"]:
            with patch.dict(os.environ, {"FORCE_HTTPS": value}, clear=True):
                result = get_app_url()
                assert result == "https://localhost:8000"

    def test_get_app_url_force_https_disabled(self):
        """Test with FORCE_HTTPS disabled."""
        for value in ["0", "false", "no", "off", "anything_else"]:
            with patch.dict(os.environ, {"FORCE_HTTPS": value}, clear=True):
                result = get_app_url()
                assert result == "http://localhost:8000"

    def test_get_app_url_logging_warning(self):
        """Test that warning is logged when APP_URL is not configured."""
        with patch('logging.warning') as mock_warning:
            with patch.dict(os.environ, {}, clear=True):
                result = get_app_url()
                assert result == "http://localhost:8000"
                mock_warning.assert_called_once()


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

    def test_get_frontend_url_with_trailing_spaces(self):
        """Test with origins that have trailing spaces."""
        with patch.dict(os.environ, {"CORS_ALLOW_ORIGINS": "https://app.com  "}):
            result = get_frontend_url()
            assert result == "https://app.com"


class TestBuildWsUrl:
    """Test build_ws_url function."""

    def test_build_ws_url_http_to_ws(self):
        """Test converting HTTP to WebSocket."""
        result = build_ws_url("/v1/ws/care", "http://localhost:8000")
        assert result == "ws://localhost:8000/v1/ws/care"

    def test_build_ws_url_https_to_wss(self):
        """Test converting HTTPS to WSS."""
        result = build_ws_url("/v1/ws/care", "https://api.example.com")
        assert result == "wss://api.example.com/v1/ws/care"

    def test_build_ws_url_with_base_url_none(self):
        """Test with base_url=None (should use get_app_url)."""
        with patch('app.url_helpers.get_app_url', return_value="http://localhost:8000"):
            result = build_ws_url("/v1/ws/care")
            assert result == "ws://localhost:8000/v1/ws/care"

    def test_build_ws_url_with_existing_path(self):
        """Test with base URL that has existing path."""
        result = build_ws_url("/v1/ws/care", "http://localhost:8000/api")
        assert result == "ws://localhost:8000/v1/ws/care"

    def test_build_ws_url_with_complex_base_url(self):
        """Test with complex base URL."""
        result = build_ws_url("/v1/ws/care", "https://api.example.com:8443/v1")
        assert result == "wss://api.example.com:8443/v1/ws/care"

    def test_build_ws_url_with_query_params(self):
        """Test with path containing query parameters."""
        result = build_ws_url("/v1/ws/care?token=abc", "http://localhost:8000")
        assert result == "ws://localhost:8000/v1/ws/care?token=abc"


class TestBuildApiUrl:
    """Test build_api_url function."""

    def test_build_api_url_simple(self):
        """Test building simple API URL."""
        result = build_api_url("/v1/auth/login", "http://localhost:8000")
        assert result == "http://localhost:8000/v1/auth/login"

    def test_build_api_url_with_base_url_none(self):
        """Test with base_url=None (should use get_app_url)."""
        with patch('app.url_helpers.get_app_url', return_value="http://localhost:8000"):
            result = build_api_url("/v1/auth/login")
            assert result == "http://localhost:8000/v1/auth/login"

    def test_build_api_url_with_existing_path(self):
        """Test with base URL that has existing path."""
        result = build_api_url("/v1/auth/login", "http://localhost:8000/api")
        assert result == "http://localhost:8000/v1/auth/login"

    def test_build_api_url_with_query_params(self):
        """Test with path containing query parameters."""
        result = build_api_url("/v1/auth/login?redirect=/dashboard", "http://localhost:8000")
        assert result == "http://localhost:8000/v1/auth/login?redirect=/dashboard"

    def test_build_api_url_with_fragment(self):
        """Test with path containing fragment."""
        result = build_api_url("/v1/auth/login#section", "http://localhost:8000")
        assert result == "http://localhost:8000/v1/auth/login#section"


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

    def test_is_dev_environment_multiple_true(self):
        """Test with multiple development indicators."""
        with patch.dict(os.environ, {
            "PYTEST_CURRENT_TEST": "test_something",
            "FLASK_ENV": "development",
            "NODE_ENV": "production"
        }, clear=True):
            assert is_dev_environment() is True


class TestBuildOriginAwareUrl:
    """Test build_origin_aware_url function."""

    def test_build_origin_aware_url_with_origin_header(self):
        """Test with origin header."""
        request = Mock()
        request.headers = {"origin": "https://app.example.com"}
        request.url = "http://localhost:8000/api/test"
        
        result = build_origin_aware_url(request, "/login")
        assert result == "https://app.example.com/login"

    def test_build_origin_aware_url_with_referer_header(self):
        """Test with referer header when origin is missing."""
        request = Mock()
        request.headers = {"referer": "https://app.example.com/dashboard"}
        request.url = "http://localhost:8000/api/test"
        
        result = build_origin_aware_url(request, "/login")
        assert result == "https://app.example.com/login"

    def test_build_origin_aware_url_from_request_url(self):
        """Test deriving from request URL when headers are missing."""
        request = Mock()
        request.headers = {}
        request.url = "https://api.example.com:8443/v1/auth"
        
        result = build_origin_aware_url(request, "/login")
        assert result == "https://api.example.com:8443/login"

    def test_build_origin_aware_url_fallback_to_env(self):
        """Test fallback to environment variable when request parsing fails."""
        request = Mock()
        request.headers = {}
        request.url = "invalid-url"
        
        with patch.dict(os.environ, {"APP_URL": "https://fallback.example.com"}):
            with patch('logging.warning') as mock_warning:
                result = build_origin_aware_url(request, "/login")
                assert result == "https://fallback.example.com/login"
                mock_warning.assert_called_once()

    def test_build_origin_aware_url_invalid_path(self):
        """Test with invalid path that doesn't start with /."""
        request = Mock()
        request.headers = {"origin": "https://app.example.com"}
        
        with pytest.raises(ValueError, match="Path must start with / for security"):
            build_origin_aware_url(request, "login")

    def test_build_origin_aware_url_with_query_params(self):
        """Test with path containing query parameters."""
        request = Mock()
        request.headers = {"origin": "https://app.example.com"}
        
        result = build_origin_aware_url(request, "/login?error=oauth_failed&next=/dashboard")
        assert result == "https://app.example.com/login?error=oauth_failed&next=/dashboard"



    def test_build_origin_aware_url_request_url_parsing_exception(self):
        """Test when request URL parsing fails."""
        request = Mock()
        request.headers = {}
        request.url = "invalid-url"
        
        with patch.dict(os.environ, {"APP_URL": "https://fallback.example.com"}):
            with patch('logging.warning') as mock_warning:
                result = build_origin_aware_url(request, "/login")
                assert result == "https://fallback.example.com/login"
                mock_warning.assert_called_once()

    def test_build_origin_aware_url_invalid_url_scheme(self):
        """Test with invalid URL scheme."""
        request = Mock()
        request.headers = {}
        request.url = "ftp://invalid-scheme.com"
        
        with patch.dict(os.environ, {"APP_URL": "https://fallback.example.com"}):
            with patch('logging.warning') as mock_warning:
                result = build_origin_aware_url(request, "/login")
                assert result == "https://fallback.example.com/login"
                mock_warning.assert_called_once()

    def test_build_origin_aware_url_no_fallback_env(self):
        """Test when no APP_URL environment variable is set."""
        request = Mock()
        request.headers = {}
        request.url = "invalid-url"
        
        with patch.dict(os.environ, {}, clear=True):
            with patch('logging.warning') as mock_warning:
                result = build_origin_aware_url(request, "/login")
                assert result == "http://localhost:3000/login"
                mock_warning.assert_called_once()


class TestSanitizeRedirectPath:
    """Test sanitize_redirect_path function."""

    def test_sanitize_redirect_path_valid_paths(self):
        """Test with valid paths."""
        assert sanitize_redirect_path("/dashboard") == "/dashboard"
        assert sanitize_redirect_path("/login?next=/app") == "/login?next=/app"
        assert sanitize_redirect_path("/api/v1/users") == "/api/v1/users"
        assert sanitize_redirect_path("/") == "/"

    def test_sanitize_redirect_path_absolute_urls(self):
        """Test with absolute URLs (should be rejected)."""
        assert sanitize_redirect_path("http://evil.com/login") == "/"
        assert sanitize_redirect_path("https://evil.com/login") == "/"
        assert sanitize_redirect_path("ftp://evil.com/login") == "/"

    def test_sanitize_redirect_path_protocol_relative_urls(self):
        """Test with protocol-relative URLs (should be rejected)."""
        assert sanitize_redirect_path("//evil.com/login") == "/"
        assert sanitize_redirect_path("//evil.com/login") == "/"

    def test_sanitize_redirect_path_invalid_inputs(self):
        """Test with invalid inputs."""
        assert sanitize_redirect_path("") == "/"
        assert sanitize_redirect_path(None) == "/"
        assert sanitize_redirect_path("login") == "/"  # Missing leading slash
        assert sanitize_redirect_path("  ") == "/"

    def test_sanitize_redirect_path_normalize_slashes(self):
        """Test slash normalization."""
        assert sanitize_redirect_path("///dashboard///") == "/dashboard/"
        assert sanitize_redirect_path("//dashboard//") == "/"  # Protocol-relative URL, rejected
        assert sanitize_redirect_path("/dashboard//") == "/dashboard/"

    def test_sanitize_redirect_path_custom_fallback(self):
        """Test with custom fallback path."""
        assert sanitize_redirect_path("http://evil.com", "/login") == "/login"
        assert sanitize_redirect_path("", "/dashboard") == "/dashboard"
        assert sanitize_redirect_path(None, "/api") == "/api"

    def test_sanitize_redirect_path_trailing_slash_preservation(self):
        """Test trailing slash preservation."""
        assert sanitize_redirect_path("/dashboard/") == "/dashboard/"
        assert sanitize_redirect_path("/dashboard///") == "/dashboard/"
        assert sanitize_redirect_path("///dashboard///") == "/dashboard/"
        assert sanitize_redirect_path("/") == "/"
        assert sanitize_redirect_path("///") == "/"

    def test_sanitize_redirect_path_query_params(self):
        """Test with query parameters."""
        assert sanitize_redirect_path("/login?error=oauth_failed") == "/login?error=oauth_failed"
        assert sanitize_redirect_path("/api/users?page=1&limit=10") == "/api/users?page=1&limit=10"

    def test_sanitize_redirect_path_fragments(self):
        """Test with URL fragments."""
        assert sanitize_redirect_path("/page#section") == "/page#section"
        assert sanitize_redirect_path("/docs#installation") == "/docs#installation"

    def test_sanitize_redirect_path_complex_paths(self):
        """Test with complex paths."""
        assert sanitize_redirect_path("/api/v1/users/123/profile") == "/api/v1/users/123/profile"
        assert sanitize_redirect_path("/admin/settings/security") == "/admin/settings/security"

    def test_sanitize_redirect_path_edge_cases(self):
        """Test edge cases."""
        # Single slash
        assert sanitize_redirect_path("/") == "/"
        
        # Multiple slashes only
        assert sanitize_redirect_path("///") == "/"
        
        # Path with spaces
        assert sanitize_redirect_path("/path with spaces") == "/path with spaces"
        
        # Path with special characters
        assert sanitize_redirect_path("/api/users/123%20test") == "/api/users/123%20test"
        
        # Test the missing edge cases for trailing slash logic
        # This should trigger the "path == '/' and not has_trailing" case
        assert sanitize_redirect_path("/") == "/"
        
        # This should trigger the "has_trailing and not path.endswith('/')" case
        # Create a path that has trailing slash but gets normalized to not have one
        assert sanitize_redirect_path("///test///") == "/test/"
