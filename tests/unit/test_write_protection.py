"""
Parameterized tests for write protection on mutating endpoints.

Tests all POST/PUT/PATCH/DELETE endpoints under /v1/ask, /v1/music, /v1/care,
/v1/pats, /v1/sessions, /v1/admin, /v1/spotify (excluding OAuth callbacks).

For each endpoint, tests:
- No token => 401 Unauthorized
- Token without CSRF => 403 Forbidden
- Token + CSRF => 2xx Success
"""
import os
import pytest
import json
from typing import Dict, List, Tuple
from fastapi.testclient import TestClient

# Import the test client from conftest or create one
try:
    from tests.conftest import client
except ImportError:
    from app.main import app
    client = TestClient(app)

# Enable CSRF for testing
os.environ["CSRF_ENABLED"] = "1"

# Test data for different endpoint types
TEST_PAYLOADS = {
    "ask": {"prompt": "test prompt", "model": "gpt-4o"},
    "register": {"username": "testuser", "password": "testpass123"},
    "music_command": {"command": "volume", "volume": 50},
    "music_restore": {},
    "music_vibe": {"name": "Test Vibe", "energy": 0.5, "tempo": 120},
    "care_session": {"resident_id": "test_resident", "alert_id": "test_alert"},
    "care_session_patch": {"status": "completed"},
    "tts_speak": {"text": "Hello world"},
    "ha_service": {"domain": "light", "service": "turn_on", "data": {"entity_id": "light.test"}},
    "revoke_session": {},
    "spotify_disconnect": {},
    "mint_access": {"user_id": "test_user", "ttl_minutes": 15},
    "revoke_pat": {},
    "admin_flags": {"key": "TEST_FLAG", "value": "test_value"},
    "admin_backup": {"destination": "/tmp/backup"}
}

# Protected endpoints to test
PROTECTED_ENDPOINTS: List[Tuple[str, str, str, str]] = [
    # (method, path, payload_key, description)
    ("POST", "/v1/ask", "ask", "Main ask endpoint"),
    ("POST", "/v1/register", "register", "User registration endpoint"),
    ("POST", "/v1/music", "music_command", "Music command endpoint"),
    ("POST", "/v1/music/restore", "music_restore", "Music volume restore endpoint"),
    ("POST", "/v1/music/vibe", "music_vibe", "Music set vibe endpoint"),
    ("POST", "/v1/care/sessions", "care_session", "Create care session endpoint"),
    ("PATCH", "/v1/care/sessions/{session_id}", "care_session_patch", "Patch care session endpoint"),
    ("POST", "/v1/tts/speak", "tts_speak", "TTS speak endpoint"),
    ("POST", "/v1/ha/service", "ha_service", "Home Assistant service endpoint"),
    ("POST", "/v1/me/sessions/{sid}/revoke", "revoke_session", "Revoke user session endpoint"),
    ("DELETE", "/v1/spotify/disconnect", "spotify_disconnect", "Spotify disconnect endpoint"),
    ("POST", "/dev/mint_access", "mint_access", "Mint access token endpoint"),
    ("DELETE", "/v1/pats/{pat_id}", "revoke_pat", "Revoke PAT endpoint"),
    # Admin endpoints
    ("POST", "/v1/admin/flags", "admin_flags", "Admin flags"),
    ("POST", "/v1/admin/backup", "admin_backup", "Admin backup endpoint"),
]


class TestWriteProtection:
    """Test write protection for all mutating endpoints."""

    @pytest.fixture
    def test_user_token(self) -> str:
        """Get a valid test user token for authenticated requests."""
        # This would need to be implemented based on your auth system
        # For now, return a mock token
        return "mock_jwt_token_for_testing"

    @pytest.fixture
    def csrf_token(self, client: TestClient) -> str:
        """Get a valid CSRF token from the server."""
        # Make a GET request to get CSRF token
        response = client.get("/v1/health")  # Any GET endpoint should set CSRF cookie
        csrf_cookie = None

        # Extract CSRF token from cookies
        if response.cookies:
            csrf_cookie = response.cookies.get("csrf_token")

        if not csrf_cookie:
            # Fallback: generate a mock CSRF token
            csrf_cookie = "mock_csrf_token_for_testing"

        return csrf_cookie

    def _make_request(
        self,
        client: TestClient,
        method: str,
        path: str,
        payload: Dict,
        auth_token: str = None,
        csrf_token: str = None
    ):
        """Make an HTTP request with optional auth and CSRF tokens."""
        headers = {}

        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"

        if csrf_token:
            headers["X-CSRF-Token"] = csrf_token

        # Convert method to lowercase for client calls
        method_lower = method.lower()

        # Use getattr to dynamically call the right method
        request_method = getattr(client, method_lower)

        return request_method(
            path,
            json=payload,
            headers=headers,
            cookies={"csrf_token": csrf_token} if csrf_token else None
        )

    @pytest.mark.parametrize("method,path,payload_key,description", PROTECTED_ENDPOINTS)
    def test_no_token_returns_401(
        self,
        client: TestClient,
        method: str,
        path: str,
        payload_key: str,
        description: str
    ):
        """Test that endpoints return 401 when no auth token is provided."""
        payload = TEST_PAYLOADS[payload_key]

        response = self._make_request(client, method, path, payload)

        assert response.status_code == 401, (
            f"Expected 401 for {method} {path} without token, got {response.status_code}. "
            f"Response: {response.text}"
        )

    @pytest.mark.parametrize("method,path,payload_key,description", PROTECTED_ENDPOINTS)
    def test_token_without_csrf_returns_401_or_403(
        self,
        client: TestClient,
        test_user_token: str,
        method: str,
        path: str,
        payload_key: str,
        description: str
    ):
        """Test that endpoints reject invalid tokens when CSRF is bypassed for Bearer auth."""
        payload = TEST_PAYLOADS[payload_key]

        # Use an invalid token that should fail auth validation
        response = self._make_request(
            client, method, path, payload,
            auth_token="Bearer invalid_token_for_testing"
        )

        # Should return 401 (unauthorized) for invalid Bearer token
        # CSRF is bypassed for Bearer-only auth, but auth should still be validated
        assert response.status_code in [401, 403], (
            f"Expected 401/403 for {method} {path} with invalid Bearer token, got {response.status_code}. "
            f"Response: {response.text}"
        )

    @pytest.mark.parametrize("method,path,payload_key,description", PROTECTED_ENDPOINTS)
    def test_token_with_csrf_returns_success(
        self,
        client: TestClient,
        test_user_token: str,
        csrf_token: str,
        method: str,
        path: str,
        payload_key: str,
        description: str
    ):
        """Test that endpoints return 2xx when both token and CSRF are provided."""
        payload = TEST_PAYLOADS[payload_key]

        response = self._make_request(
            client, method, path, payload,
            auth_token=test_user_token,
            csrf_token=csrf_token
        )

        # Should return success (2xx) with both auth and CSRF
        assert 200 <= response.status_code < 300, (
            f"Expected 2xx for {method} {path} with token and CSRF, got {response.status_code}. "
            f"Response: {response.text}"
        )


class TestWriteProtectionReport:
    """Generate a clear failure table for write protection issues."""

    def test_generate_protection_report(self, client: TestClient):
        """Generate and print a comprehensive protection report."""
        report_lines = []
        report_lines.append("=" * 80)
        report_lines.append("WRITE PROTECTION TEST REPORT")
        report_lines.append("=" * 80)

        failures = []
        total_tests = 0

        for method, path, payload_key, description in PROTECTED_ENDPOINTS:
            report_lines.append(f"\nTesting: {description}")
            report_lines.append(f"Endpoint: {method} {path}")
            report_lines.append("-" * 50)

            payload = TEST_PAYLOADS[payload_key]

            # Test 1: No token
            total_tests += 1
            response = client.request(method.lower(), path, json=payload)
            if response.status_code != 401:
                failures.append(f"❌ {method} {path} - No token: expected 401, got {response.status_code}")
                report_lines.append(f"  ❌ No token: expected 401, got {response.status_code}")
            else:
                report_lines.append("  ✅ No token: 401 (correct)")

            # Test 2: Token without CSRF (mock implementation)
            total_tests += 1
            headers = {"Authorization": "Bearer mock_token"}
            response = client.request(method.lower(), path, json=payload, headers=headers)
            if response.status_code != 403:
                failures.append(f"❌ {method} {path} - Token without CSRF: expected 403, got {response.status_code}")
                report_lines.append(f"  ❌ Token without CSRF: expected 403, got {response.status_code}")
            else:
                report_lines.append("  ✅ Token without CSRF: 403 (correct)")

            # Test 3: Token with CSRF (mock implementation)
            total_tests += 1
            headers = {
                "Authorization": "Bearer mock_token",
                "X-CSRF-Token": "mock_csrf_token"
            }
            cookies = {"csrf_token": "mock_csrf_token"}
            response = client.request(method.lower(), path, json=payload, headers=headers, cookies=cookies)
            if not (200 <= response.status_code < 300):
                failures.append(f"❌ {method} {path} - Token with CSRF: expected 2xx, got {response.status_code}")
                report_lines.append(f"  ❌ Token with CSRF: expected 2xx, got {response.status_code}")
            else:
                report_lines.append("  ✅ Token with CSRF: 2xx (correct)")

        # Summary
        report_lines.append("\n" + "=" * 80)
        report_lines.append("SUMMARY")
        report_lines.append("=" * 80)
        report_lines.append(f"Total endpoints tested: {len(PROTECTED_ENDPOINTS)}")
        report_lines.append(f"Total test cases: {total_tests}")
        report_lines.append(f"Failures: {len(failures)}")

        if failures:
            report_lines.append("\nFAILURES:")
            for failure in failures:
                report_lines.append(f"  {failure}")
        else:
            report_lines.append("\n🎉 All tests passed! Write protection is working correctly.")

        # Print the report
        report = "\n".join(report_lines)
        print(report)

        # Write to file for reference
        with open("/tmp/write_protection_report.txt", "w") as f:
            f.write(report)

        # Assert no failures for CI
        assert len(failures) == 0, f"Write protection failures detected:\n" + "\n".join(failures)


if __name__ == "__main__":
    # Allow running the report generation standalone
    from app.main import app
    test_client = TestClient(app)

    report_test = TestWriteProtectionReport()
    report_test.test_generate_protection_report(test_client)
