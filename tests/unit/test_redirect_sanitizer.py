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
            # Mobile deep-link rejection
            ("app://evil.com", DEFAULT_FALLBACK),
            ("intent://evil.com#Intent;scheme=https;action=android.intent.action.VIEW;end", DEFAULT_FALLBACK),
            ("itms-services://?action=download-manifest&url=https://evil.com/manifest.plist", DEFAULT_FALLBACK),
            ("android-app://com.example.app", DEFAULT_FALLBACK),
            ("ios-app://123456789/com.example.app", DEFAULT_FALLBACK),
            ("fb://profile/12345", DEFAULT_FALLBACK),
            ("twitter://user?screen_name=evil", DEFAULT_FALLBACK),
            ("whatsapp://send?text=evil", DEFAULT_FALLBACK),
            ("tel:+1234567890", DEFAULT_FALLBACK),
            ("sms:+1234567890", DEFAULT_FALLBACK),
            ("mailto:evil@example.com", DEFAULT_FALLBACK),
            ("file:///etc/passwd", DEFAULT_FALLBACK),
            ("javascript:alert('evil')", DEFAULT_FALLBACK),
            ("data:text/html,<script>alert('evil')</script>", DEFAULT_FALLBACK),
            # Protocol-relative with app paths
            ("//evil.com/app", DEFAULT_FALLBACK),
            ("//evil.com/android-app", DEFAULT_FALLBACK),
            ("//evil.com/ios-app", DEFAULT_FALLBACK),
            ("//evil.com/intent", DEFAULT_FALLBACK),
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


class TestSafeRedirectsEnforcedFlag:
    """Test SAFE_REDIRECTS_ENFORCED feature flag behavior."""

    def test_safe_redirects_enforced_default_enabled(self, monkeypatch):
        """Test that SAFE_REDIRECTS_ENFORCED defaults to enabled (1)."""
        # Ensure clean environment
        monkeypatch.delenv("SAFE_REDIRECTS_ENFORCED", raising=False)

        # Force reload of feature flags
        import importlib
        import app.feature_flags
        importlib.reload(app.feature_flags)
        from app.feature_flags import SAFE_REDIRECTS_ENFORCED

        assert SAFE_REDIRECTS_ENFORCED is True

    def test_safe_redirects_enforced_explicit_enabled(self, monkeypatch):
        """Test that SAFE_REDIRECTS_ENFORCED=1 enables strict mode."""
        monkeypatch.setenv("SAFE_REDIRECTS_ENFORCED", "1")

        # Force reload of feature flags
        import importlib
        import app.feature_flags
        importlib.reload(app.feature_flags)
        from app.feature_flags import SAFE_REDIRECTS_ENFORCED

        assert SAFE_REDIRECTS_ENFORCED is True

    def test_safe_redirects_enforced_disabled(self, monkeypatch):
        """Test that SAFE_REDIRECTS_ENFORCED=0 disables strict mode."""
        monkeypatch.setenv("SAFE_REDIRECTS_ENFORCED", "0")

        # Force reload of feature flags
        import importlib
        import app.feature_flags
        importlib.reload(app.feature_flags)
        from app.feature_flags import SAFE_REDIRECTS_ENFORCED

        assert SAFE_REDIRECTS_ENFORCED is False

    def test_double_decode_enforced_enabled(self, monkeypatch, caplog):
        """Test double-decode rejection when SAFE_REDIRECTS_ENFORCED=1."""
        monkeypatch.setenv("SAFE_REDIRECTS_ENFORCED", "1")

        # Force reload of feature flags and redirect utils
        import importlib
        import app.feature_flags
        import app.redirect_utils
        importlib.reload(app.feature_flags)
        importlib.reload(app.redirect_utils)

        from app.redirect_utils import sanitize_redirect_path

        # Double-encoded path should be rejected
        result = sanitize_redirect_path("%252Fdashboard")
        assert result == DEFAULT_FALLBACK

    def test_double_decode_bypass_disabled(self, monkeypatch, caplog):
        """Test double-decode bypass when SAFE_REDIRECTS_ENFORCED=0."""
        monkeypatch.setenv("SAFE_REDIRECTS_ENFORCED", "0")

        # Force reload of feature flags and redirect utils
        import importlib
        import app.feature_flags
        import app.redirect_utils
        importlib.reload(app.feature_flags)
        importlib.reload(app.redirect_utils)

        from app.redirect_utils import sanitize_redirect_path

        # Double-encoded path should be allowed in compatibility mode
        with caplog.at_level("WARNING"):
            result = sanitize_redirect_path("%252Fdashboard")

        # Should succeed and return decoded path
        assert result == "/dashboard"

        # Should log a warning about bypass
        assert any("SAFE_REDIRECTS_ENFORCED disabled: allowing double-decoded redirect path" in record.message
                  for record in caplog.records)

    def test_other_security_rules_still_enforced_disabled(self, monkeypatch):
        """Test that other security rules are still enforced when flag is disabled."""
        monkeypatch.setenv("SAFE_REDIRECTS_ENFORCED", "0")

        # Force reload of feature flags and redirect utils
        import importlib
        import app.feature_flags
        import app.redirect_utils
        importlib.reload(app.feature_flags)
        importlib.reload(app.redirect_utils)

        from app.redirect_utils import sanitize_redirect_path

        # Auth paths should still be blocked
        assert sanitize_redirect_path("/login") == DEFAULT_FALLBACK
        assert sanitize_redirect_path("/v1/auth/login") == DEFAULT_FALLBACK

        # Absolute URLs should still be blocked
        assert sanitize_redirect_path("http://evil.com") == DEFAULT_FALLBACK

        # Protocol-relative URLs should still be blocked
        assert sanitize_redirect_path("//evil.com") == DEFAULT_FALLBACK

        # Only double-decode enforcement is bypassed
        assert sanitize_redirect_path("%252Fdashboard") == "/dashboard"
