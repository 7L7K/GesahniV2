"""Tests for middleware and redirect handling to ensure origin-aware URLs."""

import pytest
from unittest.mock import patch, MagicMock
import os

from app.url_helpers import build_origin_aware_url, sanitize_redirect_path


class TestOriginAwareURLs:
    """Test origin-aware URL building for redirects."""
    
    def test_build_origin_aware_url_with_origin_header(self):
        """Test building URL from Origin header."""
        request = MagicMock()
        request.headers = {"origin": "https://app.example.com"}
        request.url = "https://api.example.com/v1/auth/callback"
        
        result = build_origin_aware_url(request, "/login")
        assert result == "https://app.example.com/login"
    
    def test_build_origin_aware_url_with_referer_header(self):
        """Test building URL from Referer header when Origin is missing."""
        request = MagicMock()
        request.headers = {"referer": "https://app.example.com/some/page"}
        request.url = "https://api.example.com/v1/auth/callback"
        
        result = build_origin_aware_url(request, "/login")
        assert result == "https://app.example.com/login"
    
    def test_build_origin_aware_url_from_request_url(self):
        """Test building URL from request URL when headers are missing."""
        request = MagicMock()
        request.headers = {}
        request.url = "https://api.example.com/v1/auth/callback"
        
        result = build_origin_aware_url(request, "/login")
        assert result == "https://api.example.com/login"
    
    def test_build_origin_aware_url_fallback_to_env(self):
        """Test fallback to environment variable when all else fails."""
        request = MagicMock()
        request.headers = {}
        request.url = "not-a-valid-url"
        
        with patch.dict('os.environ', {'APP_URL': 'https://fallback.example.com'}):
            result = build_origin_aware_url(request, "/login")
            assert result == "https://fallback.example.com/login"
    
    def test_build_origin_aware_url_invalid_path(self):
        """Test that invalid paths raise ValueError."""
        request = MagicMock()
        request.headers = {"origin": "https://app.example.com"}
        
        with pytest.raises(ValueError, match="Path must start with /"):
            build_origin_aware_url(request, "login")
    
    def test_build_origin_aware_url_with_query_params(self):
        """Test building URL with query parameters."""
        request = MagicMock()
        request.headers = {"origin": "https://app.example.com"}
        
        result = build_origin_aware_url(request, "/login?error=oauth_failed&next=/dashboard")
        assert result == "https://app.example.com/login?error=oauth_failed&next=/dashboard"


class TestSanitizeRedirectPath:
    """Test redirect path sanitization."""
    
    def test_sanitize_valid_path(self):
        """Test that valid paths are returned as-is."""
        assert sanitize_redirect_path("/dashboard") == "/dashboard"
        assert sanitize_redirect_path("/login?next=/app") == "/login?next=/app"
    
    def test_sanitize_absolute_urls(self):
        """Test that absolute URLs are rejected."""
        assert sanitize_redirect_path("http://evil.com/login") == "/"
        assert sanitize_redirect_path("https://evil.com/login") == "/"
        assert sanitize_redirect_path("//evil.com/login") == "/"
    
    def test_sanitize_protocol_relative_urls(self):
        """Test that protocol-relative URLs are rejected."""
        assert sanitize_redirect_path("//evil.com/login") == "/"
    
    def test_sanitize_invalid_paths(self):
        """Test that invalid paths are rejected."""
        assert sanitize_redirect_path("") == "/"
        assert sanitize_redirect_path(None) == "/"
        assert sanitize_redirect_path("login") == "/"  # Missing leading slash
        assert sanitize_redirect_path("  ") == "/"
    
    def test_sanitize_normalize_slashes(self):
        """Test that multiple slashes are normalized."""
        assert sanitize_redirect_path("///dashboard///") == "/dashboard/"
    
    def test_sanitize_custom_fallback(self):
        """Test custom fallback path."""
        assert sanitize_redirect_path("http://evil.com", "/login") == "/login"


class TestSecurityFeatures:
    """Test security features of redirect handling."""
    
    def test_no_hardcoded_localhost_in_urls(self):
        """Test that URL helpers don't hardcode localhost."""
        request = MagicMock()
        request.headers = {"origin": "https://app.example.com"}
        
        result = build_origin_aware_url(request, "/login")
        
        # Should use the origin, not hardcoded localhost
        assert "localhost" not in result
        assert "localhost" in result
        assert result == "https://app.example.com/login"
    
    def test_open_redirect_prevention(self):
        """Test that open redirects are prevented."""
        # Test various malicious redirect attempts
        malicious_urls = [
            "http://evil.com/login",
            "https://evil.com/login", 
            "//evil.com/login",
            "javascript:alert('xss')",
            "data:text/html,<script>alert('xss')</script>"
        ]
        
        for url in malicious_urls:
            result = sanitize_redirect_path(url)
            assert result == "/", f"Failed to sanitize: {url}"
    
    def test_relative_path_acceptance(self):
        """Test that valid relative paths are accepted."""
        valid_paths = [
            "/dashboard",
            "/login?next=/app",
            "/settings/profile",
            "/api/v1/users"
        ]
        
        for path in valid_paths:
            result = sanitize_redirect_path(path)
            assert result == path, f"Failed to accept valid path: {path}"


class TestEnvironmentConfiguration:
    """Test environment configuration for redirects."""
    
    def test_app_url_fallback(self):
        """Test that APP_URL is only used as fallback."""
        with patch.dict('os.environ', {}, clear=True):
            request = MagicMock()
            request.headers = {}
            request.url = "not-a-valid-url"
            
            result = build_origin_aware_url(request, "/login")
            # Should use default fallback
            assert "localhost:3000" in result
    
    def test_environment_variable_priority(self):
        """Test that environment variables are used in correct priority."""
        request = MagicMock()
        request.headers = {}
        request.url = "not-a-valid-url"
        
        # Test with custom APP_URL
        with patch.dict('os.environ', {'APP_URL': 'https://custom.example.com'}):
            result = build_origin_aware_url(request, "/login")
            assert result == "https://custom.example.com/login"
    
    def test_origin_header_priority_over_env(self):
        """Test that Origin header takes priority over environment variables."""
        request = MagicMock()
        request.headers = {"origin": "https://app.example.com"}
        request.url = "https://api.example.com/v1/auth/callback"
        
        with patch.dict('os.environ', {'APP_URL': 'https://fallback.example.com'}):
            result = build_origin_aware_url(request, "/login")
            # Should use origin header, not environment variable
            assert result == "https://app.example.com/login"
