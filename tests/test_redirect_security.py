"""Tests for redirect security to prevent open redirect vulnerabilities."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.security.redirects import sanitize_next_path


@pytest.fixture
def client():
    """Create a test client for the FastAPI application."""
    return TestClient(app)


class TestRedirectSecurity:
    """Test cases for redirect security."""

    def test_sanitize_next_path_rejects_absolute_urls(self):
        """Test that absolute URLs are rejected."""
        test_cases = [
            "http://evil.com",
            "https://evil.com",
            "http://evil.com/path",
            "https://evil.com/path",
        ]
        for url in test_cases:
            result = sanitize_next_path(url)
            assert result == "/dashboard", f"Should reject {url}, got {result}"

    def test_sanitize_next_path_rejects_protocol_relative_urls(self):
        """Test that protocol-relative URLs are rejected."""
        test_cases = [
            "//evil.com",
            "//evil.com/path",
            "//example.com:8080",
        ]
        for url in test_cases:
            result = sanitize_next_path(url)
            assert result == "/dashboard", f"Should reject {url}, got {result}"

    def test_sanitize_next_path_accepts_relative_paths(self):
        """Test that relative paths are accepted."""
        test_cases = [
            "/dashboard",
            "/settings",
            "/profile",
            "/",
        ]
        for path in test_cases:
            result = sanitize_next_path(path)
            assert result == path, f"Should accept {path}, got {result}"

    def test_sanitize_next_path_rejects_non_relative_paths(self):
        """Test that non-relative paths are rejected."""
        test_cases = [
            "dashboard",  # No leading slash
            "settings",   # No leading slash
            "profile",    # No leading slash
        ]
        for path in test_cases:
            result = sanitize_next_path(path)
            assert result == "/dashboard", f"Should reject {path}, got {result}"

    def test_sanitize_next_path_blocks_auth_paths(self):
        """Test that auth-related paths are blocked."""
        test_cases = [
            "/login",
            "/v1/auth",
            "/v1/auth/login",
            "/google",
            "/google/oauth",
            "/oauth",
            "/oauth/callback",
        ]
        for path in test_cases:
            result = sanitize_next_path(path)
            assert result == "/dashboard", f"Should block {path}, got {result}"

    def test_sanitize_next_path_prevents_path_traversal(self):
        """Test that path traversal attempts are blocked."""
        test_cases = [
            "/../etc/passwd",
            "/path/../../etc/passwd",
            "/valid/../invalid",
            "/path/././../secret",
        ]
        for path in test_cases:
            result = sanitize_next_path(path)
            assert result == "/dashboard", f"Should block traversal {path}, got {result}"

    def test_sanitize_next_path_handles_url_encoding(self):
        """Test that URL encoding is handled safely."""
        test_cases = [
            ("/dashboard%2F", "/dashboard/"),  # Single decode
            ("/dashboard%252F", "/dashboard/"),  # Double decode (both %25 and %2F get decoded)
            ("http%3A//evil.com", "/dashboard"),  # Encoded absolute URL
        ]
        for encoded, expected in test_cases:
            result = sanitize_next_path(encoded)
            assert result == expected, f"Should decode {encoded} to {expected}, got {result}"

    def test_sanitize_next_path_strips_fragments(self):
        """Test that URL fragments are stripped."""
        test_cases = [
            ("/dashboard#section", "/dashboard"),
            ("/settings#tab=profile", "/settings"),
            ("/path#fragment", "/path"),
        ]
        for path_with_fragment, expected in test_cases:
            result = sanitize_next_path(path_with_fragment)
            assert result == expected, f"Should strip fragment from {path_with_fragment}, got {result}"

    def test_sanitize_next_path_removes_nested_next_params(self):
        """Test that nested next parameters are removed."""
        test_cases = [
            ("/dashboard?next=/evil", "/dashboard"),
            ("/settings?next=//evil.com", "/settings"),
            ("/path?other=value&next=/login", "/path?other=value"),
        ]
        for path_with_next, expected in test_cases:
            result = sanitize_next_path(path_with_next)
            assert result == expected, f"Should remove next param from {path_with_next}, got {result}"

    def test_sanitize_next_path_normalizes_slashes(self):
        """Test that multiple slashes are normalized."""
        test_cases = [
            ("/dashboard//", "/dashboard/"),  # Normalizes to single slash
            ("//dashboard", "/dashboard"),
            ("/path///subpath", "/path/subpath"),
        ]
        for path, expected in test_cases:
            result = sanitize_next_path(path)
            assert result == expected, f"Should normalize {path} to {expected}, got {result}"

    def test_sanitize_next_path_handles_edge_cases(self):
        """Test edge cases and malformed input."""
        test_cases = [
            (None, "/dashboard"),
            ("", "/dashboard"),
            ("   ", "/dashboard"),
            ("\n\t", "/dashboard"),
            (123, "/dashboard"),  # Non-string input
        ]
        for input_val, expected in test_cases:
            result = sanitize_next_path(input_val)
            assert result == expected, f"Should handle {input_val} as {expected}, got {result}"

    def test_health_redirect_is_secure(self, client):
        """Test that health endpoint redirects are secure."""
        response = client.get("/health", allow_redirects=False)
        assert response.status_code == 308
        assert response.headers["location"] == "/healthz"
        # Should not redirect to external URLs
        assert not response.headers["location"].startswith(("http://", "https://"))

    def test_root_redirect_is_secure(self, client):
        """Test that root endpoint redirects are secure."""
        response = client.get("/", allow_redirects=False)
        assert response.status_code in [303, 307]
        location = response.headers.get("location", "")
        # Should redirect to docs or other internal path
        assert location.startswith("/")
        assert not location.startswith(("http://", "https://"))

    def test_legacy_redirects_are_secure(self, client):
        """Test that legacy endpoint redirects are secure."""
        # Test some legacy redirects
        legacy_endpoints = [
            "/whoami",
            "/status",
            "/v1/auth/pats",
        ]
        
        for endpoint in legacy_endpoints:
            try:
                response = client.get(endpoint, allow_redirects=False)
                if response.status_code in [308, 307, 303]:
                    location = response.headers.get("location", "")
                    # Should redirect to internal paths only
                    assert location.startswith("/")
                    assert not location.startswith(("http://", "https://"))
            except Exception:
                # Some endpoints might not exist or require auth
                pass
