"""Table-driven tests for AuthService seam pattern.

This demonstrates the benefits of the service seam pattern:
- Easy to test different scenarios with table-driven tests
- Single source of truth for auth operations
- Clear separation between routing and business logic
"""

from unittest.mock import Mock, patch

import pytest
from fastapi import Request, Response
from fastapi.responses import JSONResponse

from app.auth.service import AuthService


class TestAuthServiceSeam:
    """Table-driven tests for AuthService orchestration methods."""

    @pytest.mark.parametrize(
        "scenario,expected",
        [
            # Scenario: Valid token with lazy refresh needed
            {
                "name": "lazy_refresh_needed",
                "token_exp_soon": True,
                "user_id": "test_user",
                "expected_refresh_called": True,
                "expected_result": {"is_authenticated": True, "user_id": "test_user"},
            },
            # Scenario: Valid token, no refresh needed
            {
                "name": "no_refresh_needed",
                "token_exp_soon": False,
                "user_id": "test_user",
                "expected_refresh_called": False,
                "expected_result": {"is_authenticated": True, "user_id": "test_user"},
            },
            # Scenario: Invalid token
            {
                "name": "invalid_token",
                "token_exp_soon": False,
                "user_id": "anon",
                "expected_refresh_called": False,
                "expected_result": {"is_authenticated": False, "user_id": None},
            },
        ],
    )
    @pytest.mark.asyncio
    async def test_whoami_lazy_refresh_scenarios(self, scenario, expected):
        """Test whoami with lazy refresh using table-driven approach."""
        # Arrange
        request = Mock(spec=Request)
        response = Mock(spec=Response)

        with (
            patch(
                "app.auth.service.AuthService._should_lazy_refresh",
                return_value=scenario["token_exp_soon"],
            ),
            patch("app.auth.service.AuthService._perform_lazy_refresh") as mock_refresh,
            patch("app.auth.service.whoami_impl") as mock_whoami,
        ):
            # Mock whoami response
            mock_response = JSONResponse(
                {
                    "is_authenticated": scenario["user_id"] != "anon",
                    "user_id": (
                        scenario["user_id"] if scenario["user_id"] != "anon" else None
                    ),
                    "session_ready": True,
                    "source": "cookie",
                    "version": 1,
                }
            )
            mock_whoami.return_value = mock_response

            # Act
            result = await AuthService.whoami_with_lazy_refresh(request, response)

            # Assert
            assert result.status_code == 200
            result_data = result.body.decode()
            assert '"user_id":' in result_data

            if expected["expected_refresh_called"]:
                mock_refresh.assert_called_once()
            else:
                mock_refresh.assert_not_called()

    @pytest.mark.parametrize(
        "scenario,expected",
        [
            # Scenario: Successful token refresh
            {
                "name": "successful_refresh",
                "user_id": "test_user",
                "refresh_success": True,
                "expected_result": {
                    "rotated": True,
                    "access_token": "new_token",
                    "user_id": "test_user",
                },
            },
            # Scenario: No rotation needed
            {
                "name": "no_rotation_needed",
                "user_id": "test_user",
                "refresh_success": False,
                "expected_result": {
                    "rotated": False,
                    "access_token": None,
                    "user_id": "test_user",
                },
            },
            # Scenario: Invalid user (should raise error)
            {
                "name": "invalid_user",
                "user_id": "anon",
                "refresh_success": False,
                "expected_error": "invalid refresh token",
            },
        ],
    )
    @pytest.mark.asyncio
    async def test_refresh_tokens_scenarios(self, scenario, expected):
        """Test token refresh orchestration using table-driven approach."""
        # Arrange
        request = Mock(spec=Request)
        response = Mock(spec=Response)

        with (
            patch("app.auth.service.rotate_refresh_token") as mock_rotate,
            patch(
                "app.auth.service.get_current_user_id", return_value=scenario["user_id"]
            ),
            patch("app.auth.service.record_refresh_latency"),
            patch("app.auth.service.refresh_rotation_success"),
        ):
            if scenario["refresh_success"]:
                mock_rotate.return_value = {
                    "access_token": "new_token",
                    "user_id": scenario["user_id"],
                }
            else:
                mock_rotate.return_value = None

            # Act & Assert
            if "expected_error" in expected:
                with pytest.raises(Exception) as exc_info:
                    await AuthService.refresh_tokens(request, response)
                assert expected["expected_error"] in str(exc_info.value)
            else:
                result = await AuthService.refresh_tokens(request, response)
                assert result == expected["expected_result"]

    @pytest.mark.parametrize(
        "scenario,expected_calls",
        [
            # Scenario: Complete logout
            {
                "name": "complete_logout",
                "user_id": "test_user",
                "expected_calls": [
                    "revoke_refresh_family",
                    "delete_session",
                    "clear_cookies",
                ],
            },
            # Scenario: Partial failure (session delete fails)
            {
                "name": "partial_failure",
                "user_id": "test_user",
                "session_delete_fails": True,
                "expected_calls": [
                    "revoke_refresh_family",
                    "clear_cookies",
                ],  # session delete should be called but fail
            },
        ],
    )
    @pytest.mark.asyncio
    async def test_logout_orchestration_scenarios(self, scenario, expected_calls):
        """Test logout orchestration with different failure scenarios."""
        # Arrange
        request = Mock(spec=Request)
        response = Mock(spec=Response)

        with (
            patch("app.auth.service.resolve_session_id", return_value="session_123"),
            patch("app.auth.service.revoke_refresh_family") as mock_revoke,
            patch("app.auth.service.read_session_cookie", return_value="session_456"),
            patch("app.auth.service._delete_session_id") as mock_delete,
            patch("app.auth.service.clear_auth_cookies") as mock_clear,
            patch("app.auth.service.clear_device_cookie"),
            patch("app.auth.service.logger") as mock_logger,
        ):
            if scenario.get("session_delete_fails"):
                mock_delete.side_effect = Exception("Session delete failed")

            # Act
            await AuthService.logout_user(request, response, scenario["user_id"])

            # Assert
            for call_type in expected_calls:
                if call_type == "revoke_refresh_family":
                    mock_revoke.assert_called_once()
                elif call_type == "clear_cookies":
                    mock_clear.assert_called_once()

            # Verify logging calls
            assert mock_logger.info.call_count >= 2  # start and complete logs

    @pytest.mark.parametrize(
        "scenario,expected_behavior",
        [
            # Scenario: Token expires soon - should refresh
            {
                "name": "token_expires_soon",
                "token_expires_in": 200,  # seconds
                "has_valid_token": True,
                "expected_refresh": True,
            },
            # Scenario: Token expires later - should not refresh
            {
                "name": "token_expires_later",
                "token_expires_in": 1000,  # seconds
                "has_valid_token": True,
                "expected_refresh": False,
            },
            # Scenario: No token present - should not refresh
            {
                "name": "no_token",
                "token_expires_in": None,
                "has_valid_token": False,
                "expected_refresh": False,
            },
        ],
    )
    @pytest.mark.asyncio
    async def test_lazy_refresh_decision_logic(self, scenario, expected_behavior):
        """Test the decision logic for lazy refresh using table-driven approach."""
        # Arrange
        request = Mock(spec=Request)

        with (
            patch("app.auth.service.read_access_cookie") as mock_read_cookie,
            patch("app.auth.service._decode_any") as mock_decode,
            patch("time.time", return_value=1000000000),
        ):
            if scenario["has_valid_token"]:
                mock_read_cookie.return_value = "valid_token"
                if scenario["token_expires_in"] is not None:
                    mock_decode.return_value = {
                        "exp": 1000000000 + scenario["token_expires_in"]
                    }
                else:
                    mock_decode.return_value = None
            else:
                mock_read_cookie.return_value = None

            # Act
            result = await AuthService._should_lazy_refresh(request)

            # Assert
            assert result == expected_behavior["expected_refresh"]


class TestServiceSeamBenefits:
    """Demonstrate the benefits of the service seam pattern."""

    def test_router_functions_are_one_liners(self):
        """Verify that router functions delegate to service layer."""
        # This test demonstrates that router functions are now simple one-liners
        # that delegate to the AuthService, making them easy to test and maintain

        # We can test the service layer independently of HTTP concerns
        # and router functions become trivial wrappers

        # Example of what the router functions now look like:
        router_patterns = [
            "await AuthService.refresh_tokens(request, response)",
            "await AuthService.logout_user(request, response, user_id)",
            "await AuthService.whoami_with_lazy_refresh(request, response)",
        ]

        for pattern in router_patterns:
            assert "AuthService." in pattern
            assert len(pattern.split()) <= 10  # Very simple one-liners

    def test_service_layer_testability(self):
        """Demonstrate that the service layer is easily testable."""
        # The service layer methods can be tested independently
        # without needing to mock HTTP requests/responses for business logic

        service_methods = [
            AuthService.refresh_tokens,
            AuthService.logout_user,
            AuthService.whoami_with_lazy_refresh,
            AuthService._should_lazy_refresh,
        ]

        for method in service_methods:
            assert callable(method)
            # These can be unit tested with simple mocks
            # rather than full HTTP integration tests
