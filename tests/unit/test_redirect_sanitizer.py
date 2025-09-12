"""
Unit tests for redirect sanitizer with parameterized cases.

Tests the sanitize_redirect_path function with various input scenarios
to ensure proper sanitization and security.
"""

import pytest

from app.redirect_utils import DEFAULT_FALLBACK, sanitize_redirect_path


class TestRedirectSanitizer:
    """Test redirect sanitizer with parameterized test cases."""

    @pytest.mark.parametrize(
        "input_path,expected",
        [
            # None input
            (None, DEFAULT_FALLBACK),
            # Root path
            ("/", "/"),
            # Valid dashboard path
            ("/dashboard", "/dashboard"),
            # Blocked auth paths
            ("/v1/auth/refresh", DEFAULT_FALLBACK),
            ("/login", DEFAULT_FALLBACK),
            ("/login?next=%2Fdashboard", DEFAULT_FALLBACK),
            ("/x?next=%2Flogin", "/x"),
            # URL encoded paths
            ("%2Fdashboard", "/dashboard"),
            ("%252Fdashboard", "/dashboard"),
            # Malicious URLs
            ("http://evil.com/", DEFAULT_FALLBACK),
            ("//evil.com/", DEFAULT_FALLBACK),
            # Path normalization
            ("/deep//path", "/deep/path"),
            # Empty/whitespace inputs
            ("", DEFAULT_FALLBACK),
            ("   ", DEFAULT_FALLBACK),
            # Non-slash start
            ("dashboard", DEFAULT_FALLBACK),
            ("relative/path", DEFAULT_FALLBACK),
            ("./dashboard", DEFAULT_FALLBACK),
            ("../settings", DEFAULT_FALLBACK),
            # Fragment stripping
            ("/dashboard#section", "/dashboard"),
            ("/settings?tab=profile#anchor", "/settings?tab=profile"),
            # Nested next removal
            ("/dashboard?next=%2Fsettings", "/dashboard"),
            ("/path?other=param&next=%2Fevil", "/path?other=param"),
            # Double encoding handling
            ("%252Fdashboard", "/dashboard"),
            ("%252Flogin", DEFAULT_FALLBACK),
            # Slash normalization edge cases
            ("/path//to///resource", "/path/to/resource"),
            ("///dashboard", "/dashboard"),
            # Path traversal protection
            ("/../../../etc/passwd", DEFAULT_FALLBACK),
            ("/path/../../../root", DEFAULT_FALLBACK),
            # Protocol-relative rejection
            ("//evil.com", DEFAULT_FALLBACK),
            ("///evil.com", "/evil.com"),
            # Auth path variations
            ("/v1/auth/login", DEFAULT_FALLBACK),
            ("/v1/auth/logout", DEFAULT_FALLBACK),
            ("/v1/auth/csrf", DEFAULT_FALLBACK),
            ("/google", DEFAULT_FALLBACK),
            ("/oauth", DEFAULT_FALLBACK),
            ("/sign-in", DEFAULT_FALLBACK),
            ("/sign-up", DEFAULT_FALLBACK),
            # Valid paths with query params
            ("/settings/profile", "/settings/profile"),
            ("/chat?tab=general", "/chat?tab=general"),
            # Complex nested next scenarios
            ("/login?next=%2Flogin%3Fnext%3D%252Fdashboard", DEFAULT_FALLBACK),
            ("/dashboard?next=%2Fsettings%26other%3Dparam", "/dashboard?other=param"),
        ],
    )
    def test_sanitize_redirect_path(self, input_path, expected):
        """Test sanitize_redirect_path with various input scenarios."""
        result = sanitize_redirect_path(input_path)
        assert result == expected, f"Failed for input: {input_path}"

    def test_custom_fallback(self):
        """Test custom fallback parameter."""
        custom_fallback = "/custom"
        assert sanitize_redirect_path("", custom_fallback) == custom_fallback
        assert sanitize_redirect_path("/login", custom_fallback) == custom_fallback
        assert (
            sanitize_redirect_path("invalid-path", custom_fallback) == custom_fallback
        )

    def test_path_validation_edge_cases(self):
        """Test additional edge cases for path validation."""
        # Unicode and special characters
        assert sanitize_redirect_path("/café", "/café") == "/café"
        assert (
            sanitize_redirect_path("/path with spaces", "/path with spaces")
            == "/path with spaces"
        )

        # Very long paths (should still work)
        long_path = "/dashboard" + "/sub" * 100
        assert sanitize_redirect_path(long_path) == long_path

        # Paths with encoded special characters
        assert sanitize_redirect_path("/path%20with%20spaces") == "/path with spaces"
        assert sanitize_redirect_path("/path%2Bwith%2Bplus") == "/path+with+plus"

    def test_auth_path_detection(self):
        """Test auth path detection logic."""
        from app.redirect_utils import is_auth_path

        # Should be auth paths
        assert is_auth_path("/login") is True
        assert is_auth_path("/v1/auth/login") is True
        assert is_auth_path("/v1/auth/logout") is True
        assert is_auth_path("/v1/auth/refresh") is True
        assert is_auth_path("/google") is True
        assert is_auth_path("/oauth") is True

        # Should not be auth paths
        assert is_auth_path("/dashboard") is False
        assert is_auth_path("/settings") is False
        assert is_auth_path("/") is False
        assert is_auth_path("/some/path/login") is True  # Contains auth pattern
        assert is_auth_path("/secure/google/oauth") is True  # Contains auth pattern

    def test_url_decoding_safety(self):
        """Test URL decoding safety limits."""
        from app.redirect_utils import safe_decode_url

        # Normal decoding
        assert safe_decode_url("%2Fdashboard") == "/dashboard"

        # Double decoding
        assert safe_decode_url("%252Fdashboard") == "/dashboard"

        # Triple encoding should stop at double decode
        assert safe_decode_url("%2525252Fdashboard", max_decodes=2) == "%252Fdashboard"

        # Max decodes limit
        deeply_encoded = "%2525252Fdashboard"  # Triple encoded
        result = safe_decode_url(deeply_encoded, max_decodes=2)
        assert result == "%252Fdashboard"  # Only decoded twice
