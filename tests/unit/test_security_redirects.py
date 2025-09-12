"""
Unit tests for security redirect sanitization.

Tests the safe redirect functions that prevent open redirects and nesting loops.
"""

from app.security.redirects import (
    DEFAULT_REDIRECT,
    is_blocklisted_path,
    safe_decode_url,
    sanitize_next_path,
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


class TestIsBlocklistedPath:
    """Test blocklisted path detection."""

    def test_blocklisted_paths(self):
        """Test that blocklisted paths are correctly identified."""
        assert is_blocklisted_path("/login") is True
        assert is_blocklisted_path("/v1/auth") is True
        assert is_blocklisted_path("/v1/auth/login") is True
        assert is_blocklisted_path("/v1/auth/logout") is True
        assert is_blocklisted_path("/v1/auth/refresh") is True
        assert is_blocklisted_path("/v1/auth/csrf") is True
        assert is_blocklisted_path("/google") is True
        assert is_blocklisted_path("/oauth") is True
        assert is_blocklisted_path("/oauth/callback") is True

    def test_non_blocklisted_paths(self):
        """Test that non-blocklisted paths are not identified as blocked."""
        assert is_blocklisted_path("/dashboard") is False
        assert is_blocklisted_path("/settings") is False
        assert is_blocklisted_path("/profile") is False
        assert is_blocklisted_path("/") is False
        assert is_blocklisted_path("/v1/api/status") is False
        assert is_blocklisted_path("/goog") is False  # Partial but not prefix
        assert is_blocklisted_path("/log") is False  # Partial but not prefix

    def test_exact_vs_prefix_matches(self):
        """Test exact matches vs prefix matches."""
        # Exact matches
        assert is_blocklisted_path("/login") is True
        assert is_blocklisted_path("/google") is True
        assert is_blocklisted_path("/oauth") is True

        # Prefix matches
        assert is_blocklisted_path("/login/page") is True
        assert is_blocklisted_path("/v1/auth/anything") is True
        assert is_blocklisted_path("/google/oauth") is True
        assert is_blocklisted_path("/oauth/redirect") is True

        # Non-matches
        assert is_blocklisted_path("/login2") is False
        assert is_blocklisted_path("/v1/auth2") is False
        assert is_blocklisted_path("/google2") is False


class TestSanitizeNextPath:
    """Test redirect path sanitization."""

    def test_none_input(self):
        """Test None input returns fallback."""
        assert sanitize_next_path(None) == DEFAULT_REDIRECT

    def test_empty_input(self):
        """Test empty input returns fallback."""
        assert sanitize_next_path("") == DEFAULT_REDIRECT
        assert sanitize_next_path("   ") == DEFAULT_REDIRECT

    def test_valid_relative_paths(self):
        """Test valid relative paths are accepted."""
        assert sanitize_next_path("/dashboard") == "/dashboard"
        assert sanitize_next_path("/settings/profile") == "/settings/profile"
        assert sanitize_next_path("/chat?tab=general") == "/chat?tab=general"

    def test_absolute_urls_rejected(self):
        """Test absolute URLs are rejected."""
        assert sanitize_next_path("https://evil.com") == DEFAULT_REDIRECT
        assert sanitize_next_path("http://evil.com/path") == DEFAULT_REDIRECT
        assert sanitize_next_path("//evil.com/path") == DEFAULT_REDIRECT

    def test_protocol_relative_rejected(self):
        """Test protocol-relative URLs are rejected."""
        assert sanitize_next_path("//evil.com") == DEFAULT_REDIRECT
        assert sanitize_next_path("///evil.com") == "/evil.com"  # Triple slash is valid

    def test_non_slash_start_rejected(self):
        """Test paths not starting with / are rejected."""
        assert sanitize_next_path("dashboard") == DEFAULT_REDIRECT
        assert sanitize_next_path("relative/path") == DEFAULT_REDIRECT
        assert sanitize_next_path("./dashboard") == DEFAULT_REDIRECT
        assert sanitize_next_path("../settings") == DEFAULT_REDIRECT

    def test_blocklisted_paths_rejected(self):
        """Test blocklisted paths are rejected to prevent redirect loops."""
        assert sanitize_next_path("/login") == DEFAULT_REDIRECT
        assert sanitize_next_path("/v1/auth/login") == DEFAULT_REDIRECT
        assert sanitize_next_path("/google") == DEFAULT_REDIRECT
        assert sanitize_next_path("/oauth") == DEFAULT_REDIRECT
        assert sanitize_next_path("/login/page") == DEFAULT_REDIRECT
        assert sanitize_next_path("/v1/auth/anything") == DEFAULT_REDIRECT

    def test_fragment_stripping(self):
        """Test that fragments are stripped."""
        assert sanitize_next_path("/dashboard#section") == "/dashboard"
        assert (
            sanitize_next_path("/settings?tab=profile#anchor")
            == "/settings?tab=profile"
        )

    def test_nested_next_removal(self):
        """Test that nested ?next= parameters are removed."""
        assert sanitize_next_path("/dashboard?next=%2Fsettings") == "/dashboard"
        assert (
            sanitize_next_path("/path?other=param&next=%2Fevil") == "/path?other=param"
        )
        assert (
            sanitize_next_path("/path?next=%2Fgood&other=param") == "/path?other=param"
        )

    def test_double_encoding_handled(self):
        """Test that double encoding is properly handled."""
        assert sanitize_next_path("%252Fdashboard") == "/dashboard"
        assert (
            sanitize_next_path("%252Flogin") == DEFAULT_REDIRECT
        )  # Even if decoded to blocklisted path

    def test_slash_normalization(self):
        """Test that multiple slashes are normalized."""
        assert sanitize_next_path("/path//to///resource") == "/path/to/resource"
        assert sanitize_next_path("///dashboard") == "/dashboard"

    def test_path_traversal_rejected(self):
        """Test that path traversal attempts are rejected."""
        assert sanitize_next_path("/../../../etc/passwd") == DEFAULT_REDIRECT
        assert sanitize_next_path("/path/../../../root") == DEFAULT_REDIRECT

    def test_complex_queries_preserved_except_next(self):
        """Test that complex query parameters are preserved except next."""
        input_path = "/page?a=1&b=2&next=%2Fevil&c=3"
        expected = "/page?a=1&b=2&c=3"
        assert sanitize_next_path(input_path) == expected

    def test_multiple_next_params_removed(self):
        """Test that multiple next parameters are all removed."""
        input_path = "/page?next=%2Fevil1&other=param&next=%2Fevil2"
        expected = "/page?other=param"
        assert sanitize_next_path(input_path) == expected
