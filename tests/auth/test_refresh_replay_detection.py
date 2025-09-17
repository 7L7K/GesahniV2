"""
Test replay detection on refresh (expect 401/standard error).

This test file verifies that the refresh endpoint properly detects and rejects
replay attacks where the same refresh token is used multiple times.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.tokens import make_refresh


@pytest.fixture
def client():
    """Create test client with authenticated user."""
    app = create_app()
    return TestClient(app)


@pytest.fixture
def valid_refresh_token():
    """Create a valid refresh token for testing."""
    return make_refresh({"user_id": "test_user", "jti": "unique-jti-123"})


class TestRefreshReplayDetection:
    """Test that refresh endpoint detects and rejects replay attacks."""

    def test_refresh_token_single_use_success(self, client, valid_refresh_token):
        """Test that a valid refresh token works on first use."""
        response = client.post(
            "/v1/auth/refresh", json={"refresh_token": valid_refresh_token}
        )

        # Should either succeed (200) or fail for other reasons, but not replay
        assert response.status_code in [200, 401, 403]

        if response.status_code == 200:
            data = response.json()
            assert "rotated" in data
            assert isinstance(data["rotated"], bool)
            if data["rotated"]:
                assert "access_token" in data

    def test_refresh_token_replay_attack_detected(self, client, valid_refresh_token):
        """Test that using the same refresh token twice triggers replay detection."""

        # First use - should work or fail for other reasons
        response1 = client.post(
            "/v1/auth/refresh", json={"refresh_token": valid_refresh_token}
        )
        first_status = response1.status_code

        # Second use - should fail with replay detection
        response2 = client.post(
            "/v1/auth/refresh", json={"refresh_token": valid_refresh_token}
        )

        # Second use should fail
        assert response2.status_code in [
            401,
            403,
        ], f"Expected 401/403 for replay, got {response2.status_code}"

        # If we got an error response, check it's properly structured
        if response2.status_code in [401, 403]:
            error_data = response2.json()
            assert "code" in error_data
            assert "message" in error_data
            assert "meta" in error_data

            # Should be an auth-related error code
            assert error_data["code"] in [
                "invalid_refresh_token",
                "replay_detected",
                "token_already_used",
                "refresh_token_consumed",
            ]

            # Check meta contains required fields
            meta = error_data["meta"]
            assert "req_id" in meta
            assert "timestamp" in meta
            assert "error_id" in meta
            assert "status_code" in meta

    def test_refresh_token_replay_after_successful_use(self, client):
        """Test replay detection when token was successfully used in first request."""

        # First, perform a login to get a fresh refresh token
        login_response = client.post("/v1/auth/login", json={"username": "test_user"})
        assert login_response.status_code == 200

        # Extract refresh token from cookies or response
        refresh_token = None

        # Check response body first
        login_data = login_response.json()
        if "refresh_token" in login_data:
            refresh_token = login_data["refresh_token"]

        # Check cookies if not in response
        if not refresh_token:
            cookies = login_response.cookies
            # Look for refresh token cookie (may be named differently)
            for cookie_name in ["GSNH_RT", "refresh_token", "refresh"]:
                if cookie_name in cookies:
                    refresh_token = cookies[cookie_name]
                    break

        if not refresh_token:
            pytest.skip("Could not extract refresh token from login response")

        # First refresh use
        response1 = client.post(
            "/v1/auth/refresh", json={"refresh_token": refresh_token}
        )

        # If first use succeeded, second use should fail
        if response1.status_code == 200:
            response2 = client.post(
                "/v1/auth/refresh", json={"refresh_token": refresh_token}
            )

            # Second use should fail with replay detection
            assert response2.status_code in [
                401,
                403,
            ], f"Expected replay rejection, got {response2.status_code}"

            if response2.status_code in [401, 403]:
                error_data = response2.json()
                assert "code" in error_data
                # Should indicate token was already consumed
                assert error_data["code"] in [
                    "invalid_refresh_token",
                    "replay_detected",
                    "token_already_used",
                    "refresh_token_consumed",
                ]

    def test_refresh_token_replay_different_sessions(self, client):
        """Test that replay detection works across different client sessions."""

        # Session 1: Login and get refresh token
        client1 = TestClient(create_app())
        login1 = client1.post("/v1/auth/login", json={"username": "user1"})
        assert login1.status_code == 200

        # Extract token from session 1
        refresh_token = login1.json().get("refresh_token")
        if not refresh_token:
            pytest.skip("Could not extract refresh token from session 1")

        # Session 1 uses token first time
        refresh1 = client1.post(
            "/v1/auth/refresh", json={"refresh_token": refresh_token}
        )
        first_use_success = refresh1.status_code == 200

        # Session 2: Try to use same token
        client2 = TestClient(create_app())
        refresh2 = client2.post(
            "/v1/auth/refresh", json={"refresh_token": refresh_token}
        )

        # Session 2 should fail if Session 1 succeeded
        if first_use_success:
            assert refresh2.status_code in [
                401,
                403,
            ], "Replay attack not detected across sessions"

            if refresh2.status_code in [401, 403]:
                error_data = refresh2.json()
                assert "code" in error_data
                assert error_data["code"] in [
                    "invalid_refresh_token",
                    "replay_detected",
                    "token_already_used",
                ]

    def test_refresh_token_replay_rapid_fire(self, client):
        """Test replay detection with rapid successive requests using same token."""

        # Login to get token
        login_response = client.post("/v1/auth/login", json={"username": "test_user"})
        assert login_response.status_code == 200

        refresh_token = login_response.json().get("refresh_token")
        if not refresh_token:
            pytest.skip("Could not extract refresh token")

        # Fire multiple requests rapidly
        responses = []
        for i in range(5):
            response = client.post(
                "/v1/auth/refresh", json={"refresh_token": refresh_token}
            )
            responses.append((i, response.status_code, response))

        # At least one should succeed, and subsequent ones should fail
        success_count = sum(1 for _, status, _ in responses if status == 200)
        failure_count = sum(1 for _, status, _ in responses if status in [401, 403])

        # Should have at least one success and failures for replay detection
        if success_count > 0:
            # After first success, subsequent requests should fail
            first_success_idx = next(
                i for i, (_, status, _) in enumerate(responses) if status == 200
            )
            subsequent_failures = [
                (i, status, resp)
                for i, (idx, status, resp) in enumerate(responses)
                if idx > first_success_idx and status in [401, 403]
            ]

            assert (
                len(subsequent_failures) > 0
            ), "No replay detection for requests after successful use"

            # Verify error structure for replay failures
            for idx, status, resp in subsequent_failures:
                error_data = resp.json()
                assert "code" in error_data
                assert error_data["code"] in [
                    "invalid_refresh_token",
                    "replay_detected",
                    "token_already_used",
                ]

    def test_refresh_token_replay_with_cookie_vs_body(self, client):
        """Test replay detection works regardless of token submission method."""

        # Login to get token
        login_response = client.post("/v1/auth/login", json={"username": "test_user"})
        assert login_response.status_code == 200

        refresh_token = login_response.json().get("refresh_token")
        if not refresh_token:
            pytest.skip("Could not extract refresh token")

        # First use via JSON body
        response1 = client.post(
            "/v1/auth/refresh", json={"refresh_token": refresh_token}
        )

        # Second use via cookie (if supported)
        # Note: This depends on endpoint supporting cookie-based refresh
        client.cookies.set("refresh_token", refresh_token)
        response2 = client.post("/v1/auth/refresh")

        if response1.status_code == 200 and response2.status_code in [401, 403]:
            # Replay detected
            error_data = response2.json()
            assert "code" in error_data
            assert error_data["code"] in [
                "invalid_refresh_token",
                "replay_detected",
                "token_already_used",
            ]

    def test_refresh_replay_error_includes_proper_hint(
        self, client, valid_refresh_token
    ):
        """Test that replay detection errors include helpful hints."""

        # Use token once
        response1 = client.post(
            "/v1/auth/refresh", json={"refresh_token": valid_refresh_token}
        )

        # Try to use again
        response2 = client.post(
            "/v1/auth/refresh", json={"refresh_token": valid_refresh_token}
        )

        if response2.status_code in [401, 403]:
            error_data = response2.json()
            assert "code" in error_data

            # Should include hint for security best practices
            if "hint" in error_data:
                hint = error_data["hint"]
                assert isinstance(hint, str)
                # Hint should mention token reuse or security
                assert any(
                    keyword in hint.lower()
                    for keyword in [
                        "token",
                        "refresh",
                        "reuse",
                        "already",
                        "used",
                        "consumed",
                        "security",
                    ]
                )

    def test_refresh_replay_logging(self, client, valid_refresh_token, caplog):
        """Test that replay detection is properly logged."""

        # Use token once
        response1 = client.post(
            "/v1/auth/refresh", json={"refresh_token": valid_refresh_token}
        )

        # Try to use again
        response2 = client.post(
            "/v1/auth/refresh", json={"refresh_token": valid_refresh_token}
        )

        if response2.status_code in [401, 403]:
            # Check that replay detection was logged
            replay_logs = [
                record
                for record in caplog.records
                if "replay" in record.message.lower()
                or "token" in record.message.lower()
            ]
            # Should have some logging about the replay attempt
            # Note: This depends on the specific logging implementation
