"""
Unit tests for redirect utilities.

Tests the safe redirect functions that prevent open redirects and nesting loops.
"""

from unittest.mock import Mock

import pytest

from app.redirect_utils import (
    DEFAULT_FALLBACK,
    build_origin_aware_redirect_url,
    clear_gs_next_cookie,
    get_gs_next_cookie,
    get_safe_redirect_target,
    is_auth_path,
    safe_decode_url,
    sanitize_redirect_path,
    set_gs_next_cookie,
)


class TestSafeDecodeUrl:
    """Test safe URL decoding with max decode limits."""

    def test_no_encoding(self):
        """Test URL with no encoding."""
        assert safe_decode_url("/dashboard") == "/dashboard"

    def test_single_decode(self):
        """Test URL with single level of encoding."""
        assert safe_decode_url("%2Fdashboard") == "/dashboard"

    def test_double_decode(self):
        """Test URL with double encoding."""
        assert safe_decode_url("%252Fdashboard") == "/dashboard"

    def test_max_decode_limit(self):
        """Test that decoding stops at max_decodes limit."""
        # This would be %2525252F if encoded 3 times, but we limit to 2 decodes
        deeply_encoded = "%2525252Fdashboard"  # Triple encoded
        result = safe_decode_url(deeply_encoded, max_decodes=2)
        # Should decode twice but not the third time
        assert result == "%252Fdashboard"  # Only decoded twice

    def test_decode_with_spaces(self):
        """Test decoding with spaces."""
        assert safe_decode_url("hello%20world") == "hello world"
        assert (
            safe_decode_url("hello+world") == "hello+world"
        )  # + is not converted here


class TestIsAuthPath:
    """Test auth path detection."""

    def test_auth_paths(self):
        """Test that auth paths are correctly identified."""
        assert is_auth_path("/login") is True
        assert is_auth_path("/v1/auth/login") is True
        assert is_auth_path("/v1/auth/logout") is True
        assert is_auth_path("/v1/auth/refresh") is True
        assert is_auth_path("/v1/auth/csrf") is True
        assert is_auth_path("/google") is True
        assert is_auth_path("/oauth") is True
        assert is_auth_path("/sign-in") is True
        assert is_auth_path("/sign-up") is True

    def test_non_auth_paths(self):
        """Test that non-auth paths are not identified as auth paths."""
        assert is_auth_path("/dashboard") is False
        assert is_auth_path("/settings") is False
        assert is_auth_path("/profile") is False
        assert is_auth_path("/") is False

    def test_partial_matches(self):
        """Test that partial matches in paths are detected."""
        assert is_auth_path("/some/login/page") is True
        assert is_auth_path("/v1/auth/logout") is True
        assert is_auth_path("/secure/google/oauth") is True


class TestSanitizeRedirectPath:
    """Test redirect path sanitization."""

    def test_none_input(self):
        """Test None input returns fallback."""
        assert sanitize_redirect_path(None) == DEFAULT_FALLBACK

    def test_empty_input(self):
        """Test empty input returns fallback."""
        assert sanitize_redirect_path("") == DEFAULT_FALLBACK
        assert sanitize_redirect_path("   ") == DEFAULT_FALLBACK

    def test_valid_relative_paths(self):
        """Test valid relative paths are accepted."""
        assert sanitize_redirect_path("/dashboard") == "/dashboard"
        assert sanitize_redirect_path("/settings/profile") == "/settings/profile"
        assert sanitize_redirect_path("/chat?tab=general") == "/chat?tab=general"

    def test_absolute_urls_rejected(self):
        """Test absolute URLs are rejected."""
        assert sanitize_redirect_path("https://evil.com") == DEFAULT_FALLBACK
        assert sanitize_redirect_path("http://evil.com/path") == DEFAULT_FALLBACK
        assert sanitize_redirect_path("//evil.com/path") == DEFAULT_FALLBACK

    def test_protocol_relative_rejected(self):
        """Test protocol-relative URLs are rejected."""
        assert sanitize_redirect_path("//evil.com") == DEFAULT_FALLBACK
        assert (
            sanitize_redirect_path("///evil.com") == "/evil.com"
        )  # Triple slash is valid

    def test_non_slash_start_rejected(self):
        """Test paths not starting with / are rejected."""
        assert sanitize_redirect_path("dashboard") == DEFAULT_FALLBACK
        assert sanitize_redirect_path("relative/path") == DEFAULT_FALLBACK
        assert sanitize_redirect_path("./dashboard") == DEFAULT_FALLBACK
        assert sanitize_redirect_path("../settings") == DEFAULT_FALLBACK

    def test_auth_paths_rejected(self):
        """Test auth paths are rejected to prevent redirect loops."""
        assert sanitize_redirect_path("/login") == DEFAULT_FALLBACK
        assert sanitize_redirect_path("/v1/auth/login") == DEFAULT_FALLBACK
        assert sanitize_redirect_path("/google") == DEFAULT_FALLBACK
        assert sanitize_redirect_path("/sign-in") == DEFAULT_FALLBACK

    def test_fragment_stripping(self):
        """Test that fragments are stripped."""
        assert sanitize_redirect_path("/dashboard#section") == "/dashboard"
        assert (
            sanitize_redirect_path("/settings?tab=profile#anchor")
            == "/settings?tab=profile"
        )

    def test_nested_next_removal(self):
        """Test that nested ?next= parameters trigger fallback for security."""
        assert sanitize_redirect_path("/dashboard?next=%2Fsettings") == "/dashboard"
        # When next= parameters are removed, fallback to default for security
        assert (
            sanitize_redirect_path("/path?other=param&next=%2Fevil") == DEFAULT_FALLBACK
        )

    def test_double_encoding_handled(self):
        """Test that double encoding is properly handled."""
        assert sanitize_redirect_path("%252Fdashboard") == "/dashboard"
        assert (
            sanitize_redirect_path("%252Flogin") == DEFAULT_FALLBACK
        )  # Even if decoded to auth path

    def test_slash_normalization(self):
        """Test that multiple slashes are normalized."""
        assert sanitize_redirect_path("/path//to///resource") == "/path/to/resource"
        assert sanitize_redirect_path("///dashboard") == "/dashboard"

    def test_path_traversal_rejected(self):
        """Test that path traversal attempts are rejected."""
        assert sanitize_redirect_path("/../../../etc/passwd") == DEFAULT_FALLBACK
        assert sanitize_redirect_path("/path/../../../root") == DEFAULT_FALLBACK

    def test_custom_fallback(self):
        """Test custom fallback is used."""
        assert sanitize_redirect_path("", "/custom") == "/custom"
        assert sanitize_redirect_path("/login", "/custom") == "/custom"


class TestGetSafeRedirectTarget:
    """Test safe redirect target resolution."""

    def test_explicit_next_param(self):
        """Test explicit next parameter is used when valid."""
        mock_request = Mock()
        result = get_safe_redirect_target(mock_request, "/dashboard")
        assert result == "/dashboard"

    def test_invalid_next_param_falls_back(self):
        """Test invalid next parameter falls back to default."""
        mock_request = Mock()
        result = get_safe_redirect_target(
            mock_request, "/login"
        )  # Auth path should be rejected
        assert result == DEFAULT_FALLBACK

    def test_gs_next_cookie_used(self):
        """Test gs_next cookie is used when no explicit next."""
        mock_request = Mock()
        mock_request.cookies = {"gs_next": "/settings"}
        result = get_safe_redirect_target(mock_request)
        assert result == "/settings"

    def test_invalid_gs_next_falls_back(self):
        """Test invalid gs_next cookie falls back to default."""
        mock_request = Mock()
        mock_request.cookies = {"gs_next": "https://evil.com"}  # Invalid
        result = get_safe_redirect_target(mock_request)
        assert result == DEFAULT_FALLBACK

    def test_explicit_next_takes_priority(self):
        """Test explicit next parameter takes priority over cookie."""
        mock_request = Mock()
        mock_request.cookies = {"gs_next": "/cookie-target"}
        result = get_safe_redirect_target(mock_request, "/explicit-target")
        assert result == "/explicit-target"

    def test_custom_fallback(self):
        """Test custom fallback is used."""
        mock_request = Mock()
        result = get_safe_redirect_target(mock_request, None, "/custom")
        assert result == "/custom"


class TestGsNextCookie:
    """Test gs_next cookie operations."""

    def test_set_gs_next_cookie(self):
        """Test setting gs_next cookie."""
        mock_response = Mock()
        mock_response.headers = Mock()
        mock_response.headers.append = Mock()
        mock_request = Mock()

        set_gs_next_cookie(mock_response, "/dashboard", mock_request)

        # Verify cookie header was appended
        mock_response.headers.append.assert_called_once()
        call_args = mock_response.headers.append.call_args[0]
        assert call_args[0] == "set-cookie"
        cookie_value = call_args[1]
        assert "gs_next=" in cookie_value
        assert "/dashboard" in cookie_value
        assert "SameSite=Lax" in cookie_value

    def test_invalid_path_not_set(self):
        """Test invalid paths don't set cookies."""
        mock_response = Mock()
        mock_response.headers = {}
        mock_request = Mock()

        set_gs_next_cookie(mock_response, "invalid-path", mock_request)

        # No cookie should be set for invalid paths
        assert "set-cookie" not in mock_response.headers

    def test_get_gs_next_cookie(self):
        """Test getting gs_next cookie value."""
        mock_request = Mock()
        mock_request.cookies = {"gs_next": "/dashboard", "other": "value"}

        result = get_gs_next_cookie(mock_request)
        assert result == "/dashboard"

    def test_get_missing_cookie(self):
        """Test getting missing cookie returns None."""
        mock_request = Mock()
        mock_request.cookies = {"other": "value"}

        result = get_gs_next_cookie(mock_request)
        assert result is None

    def test_clear_gs_next_cookie(self):
        """Test clearing gs_next cookie."""
        mock_response = Mock()
        mock_response.headers = Mock()
        mock_response.headers.append = Mock()
        mock_request = Mock()

        clear_gs_next_cookie(mock_response, mock_request)

        # Verify cookie clear header was appended
        mock_response.headers.append.assert_called_once()
        call_args = mock_response.headers.append.call_args[0]
        assert call_args[0] == "set-cookie"
        cookie_value = call_args[1]
        assert "gs_next=" in cookie_value
        assert "Max-Age=0" in cookie_value


class TestBuildOriginAwareRedirectUrl:
    """Test origin-aware redirect URL building."""

    def test_valid_path(self):
        """Test building URL with valid path."""
        mock_request = Mock()
        mock_request.headers = {"origin": "http://localhost:3000"}
        mock_request.url = "http://localhost:3000/api/test"

        result = build_origin_aware_redirect_url(mock_request, "/dashboard")
        assert result == "http://localhost:3000/dashboard"

    def test_invalid_path_raises(self):
        """Test invalid path raises error."""
        mock_request = Mock()

        with pytest.raises(ValueError, match="Path must start with /"):
            build_origin_aware_redirect_url(mock_request, "invalid-path")

    def test_fallback_to_request_url(self):
        """Test fallback to request URL when origin not available."""
        mock_request = Mock()
        mock_request.headers = {}
        mock_request.url = "http://localhost:8000/api/test"

        result = build_origin_aware_redirect_url(mock_request, "/dashboard")
        assert result == "http://localhost:8000/dashboard"
