#!/usr/bin/env python3
"""
Cookie edge cases and integration tests.

Tests cover:
- Malformed cookies and error handling
- Cookie size limits and truncation
- Special characters in cookie values
- Concurrent cookie operations
- Cookie conflict resolution
- Performance and load testing
"""

import os
import pytest
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock

from fastapi import Request, Response, HTTPException

from app.cookie_config import format_cookie_header
from app.web.cookies import (
    ACCESS_NAME, REFRESH_NAME, SESSION_NAME,
    set_named_cookie, read_access_cookie
)
from app.auth.cookie_utils import clear_all_auth_cookies


class TestCookieErrorHandling:
    """Test cookie error handling and edge cases."""

    def test_malformed_cookie_values(self):
        """Test handling of malformed cookie values."""
        # Test with special characters
        special_values = [
            "value with spaces",
            "value;with;semicolons",
            "value=with=equals",
            "value\nwith\nnewlines",
            'value"with"quotes',
            "value\\with\\backslashes",
            "unicode_值",
            "",  # Empty value
            "x" * 4096,  # Very long value
        ]

        for value in special_values:
            header = format_cookie_header(
                key="test",
                value=value,
                max_age=3600,
                secure=False,
                samesite="lax",
                path="/"
            )
            assert "test=" in header

    def test_extreme_cookie_sizes(self):
        """Test cookie size limits."""
        # Test with maximum reasonable cookie size (4KB is typical browser limit)
        large_value = "x" * 4000

        header = format_cookie_header(
            key="large_cookie",
            value=large_value,
            max_age=3600,
            secure=False,
            samesite="lax",
            path="/"
        )

        # Should still format correctly
        assert "large_cookie=" in header
        assert len(header) > 4000  # Header includes metadata

    def test_cookie_name_validation(self):
        """Test cookie name validation."""
        valid_names = [
            "simple",
            "with_underscores",
            "with-numbers123",
            "mixed_Case_123",
        ]

        invalid_names = [
            "name with spaces",
            "name;with;semicolons",
            "name=with=equals",
            "name\nwith\nnewlines",
            'name"with"quotes',
            "",  # Empty name
        ]

        for name in valid_names:
            header = format_cookie_header(
                key=name,
                value="test",
                max_age=3600,
                secure=False,
                samesite="lax",
                path="/"
            )
            assert f"{name}=" in header

        # Invalid names should still be handled (let the browser/client validate)
        for name in invalid_names:
            if name:  # Skip empty name
                header = format_cookie_header(
                    key=name,
                    value="test",
                    max_age=3600,
                    secure=False,
                    samesite="lax",
                    path="/"
                )
                # Should still produce some kind of header
                assert "=" in header

    def test_null_bytes_in_cookies(self):
        """Test handling of null bytes in cookie values."""
        value_with_null = "value\x00with\x00nulls"

        header = format_cookie_header(
            key="null_test",
            value=value_with_null,
            max_age=3600,
            secure=False,
            samesite="lax",
            path="/"
        )

        # Should handle null bytes gracefully
        assert "null_test=" in header


class TestCookieConcurrency:
    """Test concurrent cookie operations."""

    def test_concurrent_cookie_setting(self):
        """Test setting cookies concurrently."""
        def set_cookie_task(cookie_num):
            response = Response()
            set_named_cookie(
                response=response,
                name=f"test_cookie_{cookie_num}",
                value=f"value_{cookie_num}",
                max_age=3600,
                httponly=True,
                samesite="lax",
                secure=False
            )
            return response.headers.getlist("set-cookie")

        # Run multiple cookie setting operations concurrently
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(set_cookie_task, i) for i in range(10)]
            results = [future.result() for future in futures]

        # All operations should succeed
        assert len(results) == 10
        for headers in results:
            assert headers
            assert len(headers) == 1

    def test_concurrent_cookie_reading(self):
        """Test reading cookies concurrently."""
        mock_request = Mock(spec=Request)
        mock_request.cookies = {ACCESS_NAME: "test_value"}

        def read_cookie_task():
            return read_access_cookie(mock_request)

        # Run multiple read operations concurrently
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(read_cookie_task) for _ in range(10)]
            results = [future.result() for future in futures]

        # All reads should return the same value
        assert all(result == "test_value" for result in results)


class TestCookieConflictResolution:
    """Test cookie conflict resolution."""

    def test_multiple_cookie_headers(self):
        """Test handling multiple Set-Cookie headers."""
        response = Response()

        # Set multiple cookies
        set_named_cookie(
            response=response,
            name=ACCESS_NAME,
            value="access_value",
            max_age=3600,
            httponly=True,
            samesite="lax",
            secure=False
        )

        set_named_cookie(
            response=response,
            name=REFRESH_NAME,
            value="refresh_value",
            max_age=7200,
            httponly=True,
            samesite="lax",
            secure=False
        )

        cookie_headers = response.headers.getlist("set-cookie")
        assert len(cookie_headers) == 2

        # Should contain both cookies
        header_text = " ".join(cookie_headers)
        assert ACCESS_NAME in header_text
        assert REFRESH_NAME in header_text
        assert "access_value" in header_text
        assert "refresh_value" in header_text

    def test_cookie_override_behavior(self):
        """Test cookie override behavior."""
        response = Response()

        # Set same cookie twice with different values
        set_named_cookie(
            response=response,
            name=ACCESS_NAME,
            value="first_value",
            max_age=3600,
            httponly=True,
            samesite="lax",
            secure=False
        )

        set_named_cookie(
            response=response,
            name=ACCESS_NAME,
            value="second_value",
            max_age=7200,
            httponly=True,
            samesite="lax",
            secure=False
        )

        cookie_headers = response.headers.getlist("set-cookie")

        # Should have multiple headers for same cookie (last one wins)
        access_headers = [h for h in cookie_headers if ACCESS_NAME in h]
        assert len(access_headers) >= 2

        # Last header should have the second value
        last_header = access_headers[-1]
        assert "second_value" in last_header
        assert "Max-Age=7200" in last_header


class TestCookiePerformance:
    """Test cookie operation performance."""

    def test_cookie_formatting_performance(self):
        """Test cookie header formatting performance."""
        import time

        # Format many cookies quickly
        start_time = time.time()

        for i in range(1000):
            header = format_cookie_header(
                key=f"perf_test_{i}",
                value=f"value_{i}",
                max_age=3600,
                secure=True,
                samesite="lax",
                path="/",
                httponly=True
            )
            assert header

        end_time = time.time()
        duration = end_time - start_time

        # Should complete in reasonable time (less than 1 second for 1000 operations)
        assert duration < 1.0

    def test_cookie_reading_performance(self):
        """Test cookie reading performance."""
        import time

        # Create request with many cookies
        mock_request = Mock(spec=Request)
        mock_request.cookies = {
            ACCESS_NAME: "test_value",
            "legacy_cookie_1": "legacy_1",
            "legacy_cookie_2": "legacy_2",
            "other_cookie": "other",
        }

        # Read cookie many times
        start_time = time.time()

        for _ in range(1000):
            value = read_access_cookie(mock_request)
            assert value == "test_value"

        end_time = time.time()
        duration = end_time - start_time

        # Should complete quickly
        assert duration < 0.5


class TestCookieSecurityEdgeCases:
    """Test security edge cases for cookies."""

    def test_cookie_injection_prevention(self):
        """Test prevention of cookie injection attacks."""
        malicious_values = [
            "value\r\nSet-Cookie: evil=value",
            "value\nSet-Cookie: evil=value",
            "value\rSet-Cookie: evil=value",
            "value\x00Set-Cookie: evil=value",
        ]

        for malicious_value in malicious_values:
            header = format_cookie_header(
                key="test",
                value=malicious_value,
                max_age=3600,
                secure=False,
                samesite="lax",
                path="/"
            )

            # The header should be properly escaped/formatted
            # (Note: FastAPI/Starlette handles this, we're testing our wrapper)
            assert "test=" in header
            # FastAPI should quote the value and escape CRLF to prevent header injection
            # The header should contain the quoted/escaped value
            assert "test=" in header
            # CRLF should be escaped or the value should be quoted
            assert '"value' in header or '\\015\\012' in header

    def test_host_header_attack_prevention(self):
        """Test protection against Host header attacks."""
        from app.cookie_config import get_cookie_config

        # Test with malicious host headers
        malicious_hosts = [
            "evil.com\r\nSet-Cookie: malicious=value",
            "evil.com\nSet-Cookie: malicious=value",
            "evil.com; evil.com",
            "evil.com\tevil.com",
        ]

        for malicious_host in malicious_hosts:
            mock_request = Mock(spec=Request)
            mock_request.headers = {"host": malicious_host}
            mock_request.url = Mock()
            mock_request.url.scheme = "https"

            # Should not crash and should return reasonable config
            config = get_cookie_config(mock_request)
            assert isinstance(config, dict)
            assert "domain" in config
            # Domain should be None (host-only) to prevent domain cookie attacks
            assert config["domain"] is None

    def test_cookie_name_collision_prevention(self):
        """Test prevention of cookie name collisions."""
        # Test that our canonical names don't conflict with common names
        common_names = [
            "session",
            "session_id",
            "user",
            "auth",
            "token",
            "csrf",
            "xsrf",
        ]

        canonical_names = [ACCESS_NAME, REFRESH_NAME, SESSION_NAME]

        # Canonical names should be unique and not conflict with common names
        for canonical in canonical_names:
            assert canonical not in common_names
            assert canonical.startswith("GSNH_")  # Our namespace


class TestCookieIntegrationEdgeCases:
    """Integration tests for edge cases."""

    def test_clear_all_auth_cookies(self):
        """Test clearing all authentication cookies."""
        response = Response()

        # Set all auth cookies
        set_named_cookie(response, ACCESS_NAME, "access", 3600, httponly=True, samesite="lax", path="/", secure=False)
        set_named_cookie(response, REFRESH_NAME, "refresh", 7200, httponly=True, samesite="lax", path="/", secure=False)
        set_named_cookie(response, SESSION_NAME, "session", 1800, httponly=True, samesite="lax", path="/", secure=False)

        initial_headers = len(response.headers.getlist("set-cookie"))
        assert initial_headers == 3

        # Clear all auth cookies
        clear_all_auth_cookies(response)

        final_headers = response.headers.getlist("set-cookie")
        # Should have additional clearing headers
        assert len(final_headers) > initial_headers

        # Check that clearing headers exist for each cookie
        clearing_headers = final_headers[initial_headers:]
        assert len(clearing_headers) == 3

        for header in clearing_headers:
            assert "Max-Age=0" in header

    def test_cookie_with_request_context(self):
        """Test cookie operations with real request context."""
        from fastapi.testclient import TestClient
        from app.main import create_app

        app = create_app()
        client = TestClient(app)

        # Test that cookies work in real request context
        response = client.get("/healthz/ready")

        # Should not crash
        assert response.status_code == 200

    def test_cookie_config_caching(self):
        """Test that cookie config caching works properly."""
        from app.cookie_config import get_cookie_config

        mock_request = Mock(spec=Request)
        mock_request.headers = {}

        # Get config multiple times
        config1 = get_cookie_config(mock_request)
        config2 = get_cookie_config(mock_request)

        # Should return same config (may be cached)
        assert config1 == config2
        assert isinstance(config1, dict)
        assert "secure" in config1
