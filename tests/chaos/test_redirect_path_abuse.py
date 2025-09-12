"""
Chaos test for redirect path abuse with malformed encodings and large payloads.

Tests the redirect sanitizer under extreme conditions:
- Extremely large %25 sequences
- Overlong unicode encodings
- Mixed UTF-16/UTF-8 edge cases
- Memory exhaustion attempts
- Timeout scenarios

All tests must complete without throwing, timing out, or blowing memory.
"""

import logging
import time
from unittest.mock import patch

import pytest

from app.security.redirects import DEFAULT_REDIRECT, sanitize_next_path


# Pytest markers for chaos testing
pytestmark = [
    pytest.mark.chaos,
    pytest.mark.timeout(30),  # 30 second timeout per test
    pytest.mark.memory_limit("256 MB"),  # Memory cap per test
]


class TestRedirectPathAbuse:
    """Chaos test suite for redirect path sanitization."""

    def test_extreme_percent_sequences(self):
        """Test extremely large sequences of %25 (% encoded)."""
        # Generate extremely large %25 sequences
        large_percent = "%25" * 100000  # 500,000 characters

        start_time = time.time()
        result = sanitize_next_path(large_percent)
        end_time = time.time()

        # Should return default without throwing
        assert result == DEFAULT_REDIRECT
        assert end_time - start_time < 5.0  # Should complete quickly despite size

        # Test nested encoding with large payloads
        nested_large = large_percent + "/dashboard"
        result = sanitize_next_path(nested_large)
        assert result == DEFAULT_REDIRECT

    def test_overlong_unicode_sequences(self):
        """Test overlong unicode encodings that could cause issues."""
        # Overlong UTF-8 sequences (multiple bytes for simple chars)
        overlong_sequences = [
            # Overlong slash (/)
            "%C0%AF",  # Overlong /
            "%E0%80%AF",  # Even longer overlong /
            "%F0%80%80%AF",  # Maximum overlong /

            # Overlong dot (.)
            "%C0%AE",  # Overlong .
            "%E0%80%AE",  # Longer overlong .

            # Overlong double dot (..)
            "%C0%AF%C0%AE",  # Overlong /.
            "%E0%80%AF%E0%80%AE",  # Longer overlong /.
        ]

        for seq in overlong_sequences:
            result = sanitize_next_path(seq)
            assert result == DEFAULT_REDIRECT, f"Failed for sequence: {seq}"

        # Test with path traversal attempts using overlong
        traversal_attempts = [
            "%C0%AE%C0%AE/dashboard",  # ../../dashboard with overlong
            "%E0%80%AE%E0%80%AE%E0%80%AE/dashboard",  # ../../../dashboard
        ]

        for attempt in traversal_attempts:
            result = sanitize_next_path(attempt)
            assert result == DEFAULT_REDIRECT, f"Traversal not blocked: {attempt}"

    def test_mixed_utf16_utf8_edge_cases(self):
        """Test mixed UTF-16/UTF-8 encodings and edge cases."""
        # Mixed encoding edge cases
        mixed_cases = [
            # UTF-8 encoded as UTF-16 bytes
            "%FE%FF%2F",  # UTF-16 BOM + /
            "%FF%FE%2F",  # Little endian BOM + /

            # Invalid UTF-16 sequences
            "%D8%00",  # High surrogate without low
            "%DC%00",  # Low surrogate without high
            "%D8%DC",  # Surrogate pair without continuation

            # Mixed valid/invalid UTF-16
            "%00%2F%D8%00",  # / followed by invalid surrogate

            # UTF-8 sequences interpreted as UTF-16
            "%C3%A9%E2%80%99",  # UTF-8 bytes that might confuse decoders
        ]

        for case in mixed_cases:
            result = sanitize_next_path(case)
            assert result == DEFAULT_REDIRECT, f"Failed for mixed case: {case}"

    def test_extreme_payload_sizes(self):
        """Test payloads designed to exhaust memory or cause timeouts."""
        # Generate payloads of increasing size
        sizes = [1000, 10000, 100000, 1000000]

        for size in sizes:
            # Create large payload with mixed encoding
            large_payload = ("A" * size) + "%25" * (size // 3) + "/dashboard"

            start_time = time.time()
            result = sanitize_next_path(large_payload)
            end_time = time.time()

            # Should handle gracefully without memory issues
            assert result == DEFAULT_REDIRECT
            assert end_time - start_time < 10.0, f"Too slow for size {size}"

    def test_nested_encoding_loops(self):
        """Test deeply nested URL encodings that could cause decode loops."""
        # Create nested encoding that could theoretically loop
        base = "/dashboard"
        nested = base

        # Nest encoding up to 10 levels deep
        for _ in range(10):
            nested = nested.replace("/", "%2F").replace("?", "%3F")

        # Add some circular encoding patterns
        circular_patterns = [
            "%2525" * 1000,  # %% encoded many times
            "%2525252525" * 500,  # Even deeper nesting
        ]

        for pattern in circular_patterns:
            result = sanitize_next_path(pattern)
            assert result == DEFAULT_REDIRECT

        # Test the deeply nested path
        result = sanitize_next_path(nested)
        assert result == "/dashboard", f"Failed to decode nested: {result}"

    def test_unicode_bomb_payloads(self):
        """Test unicode payloads designed to cause expansion bombs."""
        # Unicode characters that expand significantly when decoded
        expansion_chars = [
            "е",  # Cyrillic e - looks like Latin e
            "а",  # Cyrillic a - looks like Latin a
            "о",  # Cyrillic o - looks like Latin o
        ]

        # Create large strings with these characters
        for char in expansion_chars:
            large_unicode = char * 100000
            payload = large_unicode + "/dashboard"

            result = sanitize_next_path(payload)
            assert result == DEFAULT_REDIRECT

    def test_malformed_percent_encoding(self):
        """Test malformed percent encodings that could crash decoders."""
        malformed_cases = [
            # Incomplete percent sequences that should return default
            "%",  # Lone % - doesn't start with /
            "%%",  # Double % - doesn't start with /
            "%1",  # Incomplete hex - doesn't start with /
            "%XY",  # Invalid hex digits - doesn't start with /
            "%ZZ",  # Invalid hex digits - doesn't start with /

            # Percent at end of string - doesn't start with /
            "%20%XY%20/dashboard",  # Invalid hex in middle - doesn't start with /

            # Very long incomplete sequences - don't start with /
            "%" * 1000,
            ("%2" * 500) + ("%3" * 500),
        ]

        for case in malformed_cases:
            result = sanitize_next_path(case)
            assert result == DEFAULT_REDIRECT, f"Failed for malformed case: {case}"

        # These cases have valid structure but malformed encoding - sanitizer allows them
        valid_structure_cases = [
            "/dashboard%XY/extra",  # Starts with /, malformed % is preserved
            "/dashboard%",  # Starts with /
            "/dashboard%2",  # Starts with /
        ]

        for case in valid_structure_cases:
            result = sanitize_next_path(case)
            # These should pass through since they start with / and don't match blocklist
            assert result.startswith("/"), f"Should preserve valid structure: {case} -> {result}"

    def test_control_character_injection(self):
        """Test control characters that could cause parsing issues."""
        control_chars = [
            "\x00",  # Null byte
            "\x01",  # Start of heading
            "\x1F",  # Unit separator
            "\x7F",  # Delete
            "\r",    # Carriage return
            "\n",    # Line feed
            "\t",    # Tab
        ]

        for char in control_chars:
            # These should return default since they don't start with /
            invalid_payloads = [
                char + "/dashboard",  # Control char at start
                char * 1000,  # Many control characters
            ]

            for payload in invalid_payloads:
                result = sanitize_next_path(payload)
                assert result == DEFAULT_REDIRECT, f"Control char at start not rejected: {repr(char)} in {repr(payload)}"

            # These should pass through since they start with / (control chars in middle/end allowed)
            valid_payloads = [
                "/dashboard" + char,
                "/dash" + char + "board",
            ]

            for payload in valid_payloads:
                result = sanitize_next_path(payload)
                assert result.startswith("/"), f"Valid path with control char should pass: {repr(payload)} -> {result}"

    @pytest.mark.slow
    def test_memory_exhaustion_attempts(self):
        """Test payloads specifically designed to exhaust memory."""
        # These tests are marked slow and should be run separately

        # Create extremely large strings
        huge_string = "A" * 10**7  # 10 million characters

        start_time = time.time()
        result = sanitize_next_path(huge_string)
        end_time = time.time()

        assert result == DEFAULT_REDIRECT
        assert end_time - start_time < 30.0  # Should not take too long

    def test_regex_dos_patterns(self):
        """Test patterns that could cause regex denial of service."""
        # Patterns that could cause catastrophic backtracking
        dos_patterns = [
            # Complex nested query patterns - should be handled efficiently
            "?" + "&".join([f"param{i}=value{i}" for i in range(1000)]),

            # Fragments with many # symbols - should strip fragments
            "#" * 10000 + "/dashboard",
        ]

        for pattern in dos_patterns:
            start_time = time.time()
            result = sanitize_next_path(pattern)
            end_time = time.time()

            # These should complete quickly without DOS
            assert end_time - start_time < 5.0, f"Regex DOS detected for pattern: {pattern[:100]}..."

        # Test many slashes separately - sanitizer collapses them to "/"
        many_slashes = "/" * 100000
        start_time = time.time()
        result = sanitize_next_path(many_slashes)
        end_time = time.time()

        # Should collapse to "/" and complete quickly
        assert result == "/"
        assert end_time - start_time < 2.0, "Many slashes took too long to process"

    def test_encoding_edge_cases(self):
        """Test various encoding edge cases and boundary conditions."""
        edge_cases = [
            # Empty strings and whitespace
            "",
            "   ",
            "\t\n",

            # Non-string inputs (should be handled gracefully)
            None,
            123,
            [],

            # Extremely long valid paths
            "/dashboard" + "/sub" * 1000,

            # Paths with special characters
            "/dashboard?param=" + "%20" * 10000,  # Many spaces
            "/dashboard#" + "fragment" * 1000,

            # Mixed encoding types
            "/dashboard?utf8=%E2%9C%93&utf16=%FE%FF%00%2F",
        ]

        for case in edge_cases:
            try:
                result = sanitize_next_path(case)
                # Should either return default or a valid path
                assert isinstance(result, str)
                assert result.startswith("/"), f"Invalid result: {result}"
            except Exception as e:
                # Should not throw exceptions
                pytest.fail(f"Exception thrown for edge case {repr(case)}: {e}")

    def test_logging_under_load(self):
        """Test that logging doesn't break under high load."""
        with patch("app.security.redirects.logger") as mock_logger:
            # Generate many warnings/errors
            for i in range(100):
                sanitize_next_path("http://evil.com/path")  # Should trigger warning

            # Verify logging calls don't cause issues
            assert mock_logger.warning.call_count > 0

    def test_concurrent_safety(self):
        """Test that the sanitizer is safe under concurrent access."""
        import threading

        results = []
        errors = []

        def worker():
            try:
                # Each thread tests with different payloads
                payloads = [
                    "%25" * 1000,
                    "/dashboard",
                    "http://evil.com",
                    ".." * 500,
                ]

                for payload in payloads:
                    result = sanitize_next_path(payload)
                    results.append(result)

            except Exception as e:
                errors.append(e)

        # Start multiple threads
        threads = []
        for _ in range(10):
            t = threading.Thread(target=worker)
            threads.append(t)
            t.start()

        # Wait for all threads
        for t in threads:
            t.join()

        # Verify no errors occurred
        assert len(errors) == 0, f"Concurrent errors: {errors}"

        # Verify all results are valid
        for result in results:
            assert result in ["/dashboard", "/"], f"Invalid concurrent result: {result}"


if __name__ == "__main__":
    # Allow running this test directly for debugging
    pytest.main([__file__, "-v", "-s"])
