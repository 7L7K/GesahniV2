"""
Canary test for login redirect nesting prevention.

This test ensures that deeply nested next= parameters in login redirects
are properly handled and don't cause redirect loops or unexpected behavior.
"""

import pytest

from app.redirect_utils import DEFAULT_FALLBACK, sanitize_redirect_path


class TestNoLoginNextNesting:
    """Canary test to prevent regression of login next= nesting issues."""

    def test_deep_nested_next_chain_sanitized(self):
        """Test that deep nested next chains are properly sanitized."""
        # Create a deeply nested next chain (5+ levels)
        # This simulates the pattern: /login?next=/login?next=/login?next=...
        nested_url = "/login?next=%2Flogin%3Fnext%3D%252Flogin%253Fnext%253D%25252Flogin%25253Fnext%25253D%2525252Fdashboard"

        result = sanitize_redirect_path(nested_url)

        # Should fallback to default, not create a nested loop
        assert result == DEFAULT_FALLBACK
        assert result == "/dashboard"  # Explicit check for expected fallback

    def test_multiple_nested_next_parameters_removed(self):
        """Test that multiple nested next= parameters trigger fallback for security."""
        # URL with multiple next parameters at different nesting levels
        nested_url = "/login?next=%2Fdashboard%3Fnext%3D%252Fsettings%26other%3Dparam"

        result = sanitize_redirect_path(nested_url)

        # Should fallback to default when next= parameters are present (security behavior)
        assert result == DEFAULT_FALLBACK
        assert "next=" not in result

    def test_nested_next_with_auth_paths_rejected(self):
        """Test that nested next chains pointing to auth paths are rejected."""
        # Nested chain that eventually points to auth path after decoding
        nested_auth_url = "/dashboard?next=%2Flogin%3Fnext%3D%252Fgoogle"

        result = sanitize_redirect_path(nested_auth_url)

        # Should fallback because it contains auth paths in the chain
        assert result == DEFAULT_FALLBACK

    def test_deeply_encoded_auth_path_rejected(self):
        """Test that deeply encoded auth paths are properly decoded and rejected."""
        # Triple-encoded /login that should be decoded and rejected
        triple_encoded_login = (
            "%25252Flogin"  # %25 = %, so this decodes to %2Flogin -> /login
        )

        result = sanitize_redirect_path(triple_encoded_login)

        # Should decode twice and reject the auth path
        assert result == DEFAULT_FALLBACK

    def test_safe_nested_parameters_preserved(self):
        """Test that safe nested parameters (not next=) are preserved."""
        # URL with safe nested parameters
        safe_nested = "/dashboard?tab=settings&filter=active"

        result = sanitize_redirect_path(safe_nested)

        # Should preserve safe parameters
        assert result == "/dashboard?tab=settings&filter=active"

    def test_mixed_nested_next_and_safe_params(self):
        """Test mixed next= and safe parameters trigger fallback for security."""
        # Complex URL with both next= and safe parameters
        mixed_url = "/path?next=%2Fdashboard&safe=param&next=%2Fsettings"

        result = sanitize_redirect_path(mixed_url)

        # Should fallback to default when next= parameters are present (security behavior)
        assert result == DEFAULT_FALLBACK
        assert "next=" not in result

    @pytest.mark.parametrize("depth", [1, 2, 3, 4, 5, 10])
    def test_various_nesting_depths_handled(self, depth):
        """Test that nesting works correctly at various depths."""
        # Build a nested URL of specified depth
        path = "/dashboard"
        for _ in range(depth):
            path = f"/login?next={path}"

        # URL encode the nested path
        from urllib.parse import quote

        nested_url = quote(path, safe="")

        result = sanitize_redirect_path(nested_url)

        # At any depth, if it contains auth paths, should fallback
        # This test ensures we don't have infinite loops or stack overflows
        assert result in ["/dashboard", DEFAULT_FALLBACK]
        assert isinstance(result, str)
        assert result.startswith("/")

    def test_redirect_loop_prevention(self):
        """Test specific prevention of redirect loops from the original issue."""
        # Simulate the problematic pattern from the original bug
        problematic_patterns = [
            "/login?next=/login",
            "/login?next=%2Flogin",
            "/login?next=%2Flogin%3Fnext%3D%252Fdashboard",
            "/login?next=/login?next=/login?next=/dashboard",
        ]

        for pattern in problematic_patterns:
            result = sanitize_redirect_path(pattern)
            # All should fallback to prevent loops
            assert (
                result == DEFAULT_FALLBACK
            ), f"Pattern {pattern} should fallback but got {result}"

    def test_no_false_positives_on_safe_redirects(self):
        """Test that safe redirects still work correctly."""
        safe_redirects = [
            "/dashboard",
            "/settings/profile",
            "/chat?tab=general",
            "/search?q=test&page=1",
        ]

        for safe_path in safe_redirects:
            result = sanitize_redirect_path(safe_path)
            assert result == safe_path, f"Safe path {safe_path} should be preserved"

    def test_canary_assertion_final_target(self):
        """Canary assertion: final redirect target should be /dashboard without next= param."""
        # This is the core assertion that should fail loudly if the issue reappears
        test_cases = [
            # Original problematic patterns that should be caught
            "/login?next=/login",
            "/login?next=/login?next=/dashboard",
            "/login?next=%2Flogin%3Fnext%3D%252Fdashboard",
            # Edge cases with encoding
            "%2Flogin%3Fnext%3D%252Fdashboard",  # URL encoded
            "%252Flogin",  # Double encoded
        ]

        for test_case in test_cases:
            result = sanitize_redirect_path(test_case)

            # Core canary assertion: should always resolve to /dashboard without next=
            assert result == "/dashboard", (
                f"Canary test FAILED: {test_case} should resolve to /dashboard "
                f"but got {result}. This indicates a regression in redirect sanitization!"
            )

            # Additional check: no next= parameters should remain
            assert "next=" not in result, (
                f"Canary test FAILED: {test_case} still contains next= parameter "
                f"in result {result}. Nested next= parameters should be stripped!"
            )
