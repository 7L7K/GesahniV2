"""
Unit tests for OAuth structured logging.
"""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app


class TestOAuthLogging:
    """Test OAuth structured logging functionality."""

    def test_oauth_login_url_logging(self):
        """Test that oauth.login_url logs are structured correctly."""
        with patch("app.api.google_oauth.logger") as mock_logger:
            with patch.dict(
                "os.environ",
                {
                    "GOOGLE_CLIENT_ID": "test_client_id",
                    "GOOGLE_REDIRECT_URI": "http://localhost:8000/callback",
                },
            ):
                client = TestClient(app)
                response = client.get("/v1/google/auth/login_url")

                # Verify the log was called with correct structure
                mock_logger.info.assert_called()
                call_args = mock_logger.info.call_args_list

                # Find the oauth.login_url log
                oauth_log_call = None
                for call in call_args:
                    if call[0][0] == "oauth.login_url":
                        oauth_log_call = call
                        break

                assert oauth_log_call is not None, "oauth.login_url log not found"

                # Verify the meta structure
                meta = oauth_log_call[1]["extra"]["meta"]
                assert meta["msg"] == "oauth.login_url"
                assert meta["state_set"] is True
                assert meta["next"] == "/"
                assert meta["cookie_http_only"] is True
                assert meta["samesite"] == "Lax"

    def test_oauth_callback_success_logging(self):
        """Test that oauth.callback.success logs are structured correctly."""
        with patch("app.api.google_oauth.logger") as mock_logger:
            with patch("app.api.google_oauth._verify_signed_state", return_value=True):
                with patch(
                    "app.integrations.google.oauth.exchange_code"
                ) as mock_exchange:
                    # Mock successful token exchange
                    mock_creds = MagicMock()
                    mock_creds.id_token = "mock_id_token"
                    mock_exchange.return_value = mock_creds

                    with patch("jwt.decode") as mock_decode:
                        mock_decode.return_value = {
                            "email": "test@example.com",
                            "sub": "123",
                        }

                        with patch("app.api.google_oauth.set_auth_cookies"):
                            client = TestClient(app)
                            response = client.get(
                                "/v1/google/auth/callback?code=test_code&state=test_state"
                            )

                            # Verify the log was called with correct structure
                            mock_logger.info.assert_called()
                            call_args = mock_logger.info.call_args_list

                            # Find the oauth.callback.success log
                            success_log_call = None
                            for call in call_args:
                                if call[0][0] == "oauth.callback.success":
                                    success_log_call = call
                                    break

                            assert (
                                success_log_call is not None
                            ), "oauth.callback.success log not found"

                            # Verify the meta structure
                            meta = success_log_call[1]["extra"]["meta"]
                            assert meta["msg"] == "oauth.callback.success"
                            assert meta["state_valid"] is True
                            assert meta["token_exchange"] == "ok"
                            assert meta["set_auth_cookies"] is True
                            assert meta["redirect"] is not None

    def test_oauth_callback_failure_logging(self):
        """Test that oauth.callback.fail logs are structured correctly."""
        with patch("app.api.google_oauth.logger") as mock_logger:
            with patch("app.api.google_oauth._verify_signed_state", return_value=True):
                with patch(
                    "app.integrations.google.oauth.exchange_code"
                ) as mock_exchange:
                    # Mock failed token exchange
                    mock_exchange.side_effect = Exception("Token exchange failed")

                    client = TestClient(app)
                    response = client.get(
                        "/v1/google/auth/callback?code=test_code&state=test_state"
                    )

                    # Verify the log was called with correct structure
                    mock_logger.error.assert_called()
                    call_args = mock_logger.error.call_args_list

                    # Find the oauth.callback.fail log
                    fail_log_call = None
                    for call in call_args:
                        if call[0][0] == "oauth.callback.fail":
                            fail_log_call = call
                            break

                    assert (
                        fail_log_call is not None
                    ), "oauth.callback.fail log not found"

                    # Verify the meta structure
                    meta = fail_log_call[1]["extra"]["meta"]
                    assert meta["msg"] == "oauth.callback.fail"
                    assert meta["state_valid"] is True
                    assert meta["token_exchange"] == "fail"
                    assert meta["google_status"] == 500
                    assert meta["reason"] == "oauth_exchange_failed"
                    assert meta["redirect"] == "/login?err=oauth_exchange_failed"

    def test_whoami_logging(self):
        """Test that auth.whoami logs are structured correctly."""
        with patch("app.api.auth.logger") as mock_logger:
            with patch("app.deps.user.get_current_user_id", return_value="test_user"):
                client = TestClient(app)
                response = client.get("/v1/whoami")

                # Verify the log was called with correct structure
                mock_logger.info.assert_called()
                call_args = mock_logger.info.call_args_list

                # Find the auth.whoami log
                whoami_log_call = None
                for call in call_args:
                    if call[0][0] == "auth.whoami":
                        whoami_log_call = call
                        break

                assert whoami_log_call is not None, "auth.whoami log not found"

                # Verify the meta structure
                meta = whoami_log_call[1]["extra"]["meta"]
                assert meta["msg"] == "auth.whoami"
                assert meta["status"] == 200
                assert meta["user_id"] == "test_user"
                assert "duration_ms" in meta

    def test_http_out_logging(self):
        """Test that http_out logs are structured correctly for external calls."""
        with patch("app.api.google_oauth.logger") as mock_logger:
            with patch("app.api.google_oauth._verify_signed_state", return_value=True):
                with patch(
                    "app.integrations.google.oauth.exchange_code"
                ) as mock_exchange:
                    # Mock successful token exchange
                    mock_creds = MagicMock()
                    mock_creds.id_token = "mock_id_token"
                    mock_exchange.return_value = mock_creds

                    with patch("jwt.decode") as mock_decode:
                        mock_decode.return_value = {
                            "email": "test@example.com",
                            "sub": "123",
                        }

                        with patch("app.api.google_oauth.set_auth_cookies"):
                            client = TestClient(app)
                            response = client.get(
                                "/v1/google/auth/callback?code=test_code&state=test_state"
                            )

                            # Verify the http_out log was called
                            mock_logger.info.assert_called()
                            call_args = mock_logger.info.call_args_list

                            # Find the http_out log
                            http_out_log_call = None
                            for call in call_args:
                                if "http_out" in call[1].get("extra", {}).get(
                                    "meta", {}
                                ):
                                    http_out_log_call = call
                                    break

                            assert (
                                http_out_log_call is not None
                            ), "http_out log not found"

                            # Verify the http_out structure
                            meta = http_out_log_call[1]["extra"]["meta"]
                            http_out = meta["http_out"]
                            assert http_out["service"] == "google_token"
                            assert http_out["status"] == 200
                            assert "latency_ms" in http_out
