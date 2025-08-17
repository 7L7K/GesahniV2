"""
Tests for authentication monitoring system.
"""

import pytest
import time
from unittest.mock import patch, MagicMock

from app.auth_monitoring import (
    log_auth_event,
    track_auth_event,
    record_whoami_call,
    record_finish_call,
    record_privileged_call_blocked,
    record_ws_reconnect_attempt,
    record_auth_lock_event,
    record_auth_state_change,
    _is_boot_phase,
)


class TestAuthMonitoring:
    """Test authentication monitoring functionality."""

    def test_log_auth_event(self):
        """Test logging authentication events."""
        with patch('app.auth_monitoring.logger') as mock_logger:
            log_auth_event(
                event_type="whoami.call",
                user_id="test_user",
                source="cookie",
                jwt_status="ok",
                session_ready=True,
                is_authenticated=True
            )
            
            mock_logger.info.assert_called_once()
            call_args = mock_logger.info.call_args
            assert call_args[0][0] == "Authentication event"
            assert "event_type" in call_args[1]["extra"]
            assert call_args[1]["extra"]["event_type"] == "whoami.call"

    def test_track_auth_event_context_manager(self):
        """Test authentication event timing context manager."""
        with patch('app.auth_monitoring.log_auth_event') as mock_log:
            with track_auth_event("whoami", user_id="test_user"):
                time.sleep(0.01)  # Small delay to ensure timing
            
            # Should log start and end events
            assert mock_log.call_count == 2
            start_call = mock_log.call_args_list[0]
            end_call = mock_log.call_args_list[1]
            
            assert "whoami.start" in start_call[0]
            assert "whoami.end" in end_call[0]

    def test_record_whoami_call(self):
        """Test recording whoami calls with metrics."""
        with patch('app.auth_monitoring.WHOAMI_CALLS_TOTAL') as mock_counter:
            with patch('app.auth_monitoring.log_auth_event') as mock_log:
                record_whoami_call(
                    status="success",
                    source="cookie",
                    user_id="test_user",
                    session_ready=True,
                    is_authenticated=True,
                    jwt_status="ok"
                )
                
                # Should increment counter
                mock_counter.labels.assert_called_once()
                # Should log event
                mock_log.assert_called_once()

    def test_record_finish_call(self):
        """Test recording finish calls with metrics."""
        with patch('app.auth_monitoring.FINISH_CALLS_TOTAL') as mock_counter:
            with patch('app.auth_monitoring.log_auth_event') as mock_log:
                record_finish_call(
                    status="success",
                    method="POST",
                    reason="normal_login",
                    user_id="test_user",
                    set_cookie=True
                )
                
                # Should increment counter
                mock_counter.labels.assert_called_once()
                # Should log event
                mock_log.assert_called_once()

    def test_record_privileged_call_blocked(self):
        """Test recording blocked privileged calls."""
        with patch('app.auth_monitoring.PRIVILEGED_CALLS_BLOCKED_TOTAL') as mock_counter:
            with patch('app.auth_monitoring.log_auth_event') as mock_log:
                record_privileged_call_blocked(
                    endpoint="/api/protected",
                    reason="missing_token",
                    user_id="test_user"
                )
                
                # Should increment counter
                mock_counter.labels.assert_called_once()
                # Should log event
                mock_log.assert_called_once()

    def test_record_ws_reconnect_attempt(self):
        """Test recording WebSocket reconnection attempts."""
        with patch('app.auth_monitoring.WS_RECONNECT_ATTEMPTS_TOTAL') as mock_counter:
            with patch('app.auth_monitoring.log_auth_event') as mock_log:
                record_ws_reconnect_attempt(
                    endpoint="/v1/ws/music",
                    reason="connection_lost",
                    user_id="test_user"
                )
                
                # Should increment counter
                mock_counter.labels.assert_called_once()
                # Should log event
                mock_log.assert_called_once()

    def test_record_auth_lock_event(self):
        """Test recording authentication lock events."""
        with patch('app.auth_monitoring.log_auth_event') as mock_log:
            record_auth_lock_event(
                action="on",
                reason="rate_limit",
                user_id="test_user",
                duration_seconds=60.0
            )
            
            # Should log event
            mock_log.assert_called_once()
            call_args = mock_log.call_args
            assert "lock.on" in call_args[0]

    def test_record_auth_state_change(self):
        """Test recording authentication state changes."""
        with patch('app.auth_monitoring.log_auth_event') as mock_log:
            record_auth_state_change(
                old_state=False,
                new_state=True,
                user_id="test_user",
                source="cookie",
                reason="login_success"
            )
            
            # Should log event
            mock_log.assert_called_once()
            call_args = mock_log.call_args
            assert "authed.change" in call_args[0]

    def test_boot_phase_detection(self):
        """Test boot phase detection."""
        # Should be in boot phase initially
        assert _is_boot_phase() is True
        
        # After 35 seconds, should not be in boot phase
        with patch('app.auth_monitoring.time') as mock_time:
            mock_time.time.return_value = time.time() + 35
            assert _is_boot_phase() is False

    def test_error_handling(self):
        """Test error handling in monitoring functions."""
        with patch('app.auth_monitoring.logger') as mock_logger:
            with patch('app.auth_monitoring.WHOAMI_CALLS_TOTAL') as mock_counter:
                # Simulate counter error
                mock_counter.labels.side_effect = Exception("Counter error")
                
                # Should not raise exception
                record_whoami_call(
                    status="success",
                    source="cookie",
                    user_id="test_user"
                )
                
                # Should log error
                mock_logger.error.assert_called_once()
                assert "Failed to record whoami call" in mock_logger.error.call_args[0][0]


class TestAuthMonitoringIntegration:
    """Integration tests for authentication monitoring."""

    @pytest.mark.asyncio
    async def test_whoami_endpoint_monitoring(self, client):
        """Test that whoami endpoint includes monitoring."""
        with patch('app.auth_monitoring.record_whoami_call') as mock_record:
            response = await client.get("/v1/whoami")
            
            # Should record the call
            mock_record.assert_called_once()
            call_args = mock_record.call_args
            assert call_args[1]["status"] == "success"

    @pytest.mark.asyncio
    async def test_finish_endpoint_monitoring(self, client):
        """Test that finish endpoint includes monitoring."""
        with patch('app.auth_monitoring.record_finish_call') as mock_record:
            # Mock authentication for finish endpoint
            with patch('app.api.auth._require_user_or_dev') as mock_auth:
                mock_auth.return_value = "test_user"
                
                response = await client.post("/v1/auth/finish")
                
                # Should record the call
                mock_record.assert_called()

    @pytest.mark.asyncio
    async def test_privileged_call_blocking_monitoring(self, client):
        """Test that blocked privileged calls are monitored."""
        with patch('app.auth_monitoring.record_privileged_call_blocked') as mock_record:
            # Try to access protected endpoint without auth
            response = await client.get("/v1/me")
            
            # Should record the blocked call
            mock_record.assert_called()
            call_args = mock_record.call_args
            assert "missing_token" in call_args[1]["reason"]
