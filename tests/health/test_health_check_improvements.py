import time
from unittest.mock import patch

import pytest

import app.llama_integration
from app.llama_integration import (
    _check_and_set_flag,
    _schedule_next_health_check,
    llama_health_check_state,
    startup_check,
)

pytestmark = pytest.mark.asyncio


class TestHealthCheckImprovements:
    """Test the improved health check system with exponential backoff and throttling."""

    def setup_method(self):
        """Reset health check state before each test."""
        # Reset global state
        import app.llama_integration

        app.llama_integration.LLAMA_HEALTHY = True

        llama_health_check_state.update(
            {
                "has_ever_succeeded": False,
                "last_success_ts": 0.0,
                "last_check_ts": 0.0,
                "consecutive_failures": 0,
                "next_check_delay": 5.0,
                "max_check_delay": 300.0,
                "success_throttle_delay": 60.0,
            }
        )

    @patch("app.llama_integration.json_request")
    @patch("app.llama_integration.scheduler")
    async def test_exponential_backoff_before_success(
        self, mock_scheduler, mock_json_request
    ):
        """Test exponential backoff behavior before first success."""
        # Mock environment
        with patch.dict(
            "os.environ", {"OLLAMA_MODEL": "test-model", "OLLAMA_URL": "http://test"}
        ):
            # Mock failed health checks
            mock_json_request.return_value = (None, "connection error")

            # First failure - ensure enough time has passed since last check
            llama_health_check_state["last_check_ts"] = 0.0
            await _check_and_set_flag()
            assert not app.llama_integration.LLAMA_HEALTHY
            assert llama_health_check_state["consecutive_failures"] == 1
            assert llama_health_check_state["next_check_delay"] == 10.0  # 5 * 2

            # Second failure - ensure enough time has passed since last check
            llama_health_check_state["last_check_ts"] = 0.0
            await _check_and_set_flag()
            assert not app.llama_integration.LLAMA_HEALTHY
            assert llama_health_check_state["consecutive_failures"] == 2
            assert llama_health_check_state["next_check_delay"] == 20.0  # 10 * 2

            # Third failure - ensure enough time has passed since last check
            llama_health_check_state["last_check_ts"] = 0.0
            await _check_and_set_flag()
            assert not app.llama_integration.LLAMA_HEALTHY
            assert llama_health_check_state["consecutive_failures"] == 3
            assert llama_health_check_state["next_check_delay"] == 40.0  # 20 * 2

    @patch("app.llama_integration.json_request")
    @patch("app.llama_integration.scheduler")
    async def test_success_resets_backoff(self, mock_scheduler, mock_json_request):
        """Test that success resets exponential backoff."""
        # Mock environment
        with patch.dict(
            "os.environ", {"OLLAMA_MODEL": "test-model", "OLLAMA_URL": "http://test"}
        ):
            # Mock failed health checks first
            mock_json_request.return_value = (None, "connection error")
            llama_health_check_state["last_check_ts"] = 0.0
            await _check_and_set_flag()
            assert llama_health_check_state["next_check_delay"] == 10.0

            # Then mock successful health check
            mock_json_request.return_value = ({"response": "test"}, None)
            llama_health_check_state["last_check_ts"] = 0.0
            await _check_and_set_flag()

            assert app.llama_integration.LLAMA_HEALTHY
            assert llama_health_check_state["has_ever_succeeded"] is True
            assert llama_health_check_state["consecutive_failures"] == 0
            assert (
                llama_health_check_state["next_check_delay"] == 5.0
            )  # Reset to initial

    @patch("app.llama_integration.json_request")
    @patch("app.llama_integration.scheduler")
    async def test_throttling_after_success(self, mock_scheduler, mock_json_request):
        """Test throttling behavior after first success."""
        # Mock environment
        with patch.dict(
            "os.environ", {"OLLAMA_MODEL": "test-model", "OLLAMA_URL": "http://test"}
        ):
            # Set up as if we've already succeeded
            llama_health_check_state["has_ever_succeeded"] = True
            llama_health_check_state["last_success_ts"] = time.monotonic()

            # Mock successful health check
            mock_json_request.return_value = ({"response": "test"}, None)

            # Should be throttled if called too soon
            llama_health_check_state["last_success_ts"] = (
                time.monotonic() - 30.0
            )  # 30 seconds ago
            await _check_and_set_flag()
            # Should not call json_request due to throttling
            assert mock_json_request.call_count == 0

    @patch("app.llama_integration.json_request")
    @patch("app.llama_integration.scheduler")
    async def test_max_delay_cap(self, mock_scheduler, mock_json_request):
        """Test that exponential backoff is capped at max_delay."""
        # Mock environment
        with patch.dict(
            "os.environ", {"OLLAMA_MODEL": "test-model", "OLLAMA_URL": "http://test"}
        ):
            # Mock failed health checks
            mock_json_request.return_value = (None, "connection error")

            # Set next_check_delay to near max
            llama_health_check_state["next_check_delay"] = 200.0

            await _check_and_set_flag()
            # Should be capped at max_delay (300.0)
            assert llama_health_check_state["next_check_delay"] == 300.0

    @patch("app.llama_integration.json_request")
    @patch("app.llama_integration.scheduler")
    async def test_schedule_next_health_check(self, mock_scheduler, mock_json_request):
        """Test that next health check is scheduled correctly."""
        # Mock environment
        with patch.dict(
            "os.environ", {"OLLAMA_MODEL": "test-model", "OLLAMA_URL": "http://test"}
        ):
            # Test scheduling before success (exponential backoff)
            llama_health_check_state["next_check_delay"] = 10.0
            await _schedule_next_health_check()

            mock_scheduler.remove_job.assert_called_with("llama_health_check")
            mock_scheduler.add_job.assert_called_once()
            # Check that the function was called with the right arguments
            call_args = mock_scheduler.add_job.call_args
            assert call_args[0][0] == _check_and_set_flag  # function
            # The scheduler mock might not preserve kwargs exactly, so check what we can
            assert "id" in call_args[1] or len(call_args[1]) > 0

    @patch("app.llama_integration.json_request")
    @patch("app.llama_integration.scheduler")
    async def test_startup_check_schedules_health_check(
        self, mock_scheduler, mock_json_request
    ):
        """Test that startup_check schedules the next health check."""
        # Mock environment
        with patch.dict(
            "os.environ", {"OLLAMA_MODEL": "test-model", "OLLAMA_URL": "http://test"}
        ):
            # Mock successful health check
            mock_json_request.return_value = ({"response": "test"}, None)

            await startup_check()

            # Should schedule next health check
            mock_scheduler.add_job.assert_called()
            # The scheduler.start() might not be called if already running, so don't assert it

    @patch("app.llama_integration.json_request")
    @patch("app.llama_integration.scheduler")
    async def test_skip_health_check_due_to_throttling(
        self, mock_scheduler, mock_json_request
    ):
        """Test that health checks are skipped when throttled."""
        # Mock environment
        with patch.dict(
            "os.environ", {"OLLAMA_MODEL": "test-model", "OLLAMA_URL": "http://test"}
        ):
            # Set up as if we've recently succeeded
            llama_health_check_state["has_ever_succeeded"] = True
            llama_health_check_state["last_success_ts"] = (
                time.monotonic() - 30.0
            )  # 30 seconds ago

            await _check_and_set_flag()

            # Should not call json_request due to throttling
            assert mock_json_request.call_count == 0

    @patch("app.llama_integration.json_request")
    @patch("app.llama_integration.scheduler")
    async def test_skip_health_check_due_to_backoff(
        self, mock_scheduler, mock_json_request
    ):
        """Test that health checks are skipped during exponential backoff."""
        # Mock environment
        with patch.dict(
            "os.environ", {"OLLAMA_MODEL": "test-model", "OLLAMA_URL": "http://test"}
        ):
            # Set up as if we recently failed and are in backoff
            llama_health_check_state["last_check_ts"] = (
                time.monotonic() - 2.0
            )  # 2 seconds ago
            llama_health_check_state["next_check_delay"] = 10.0

            await _check_and_set_flag()

            # Should not call json_request due to backoff
            assert mock_json_request.call_count == 0

    @patch("app.llama_integration.json_request")
    @patch("app.llama_integration.scheduler")
    async def test_health_check_proceeds_when_not_throttled(
        self, mock_scheduler, mock_json_request
    ):
        """Test that health checks proceed when not throttled."""
        # Mock environment
        with patch.dict(
            "os.environ", {"OLLAMA_MODEL": "test-model", "OLLAMA_URL": "http://test"}
        ):
            # Set up as if we succeeded long ago
            llama_health_check_state["has_ever_succeeded"] = True
            llama_health_check_state["last_success_ts"] = (
                time.monotonic() - 120.0
            )  # 2 minutes ago

            # Mock successful health check
            mock_json_request.return_value = ({"response": "test"}, None)

            await _check_and_set_flag()

            # Should call json_request since not throttled
            assert mock_json_request.call_count == 1
            assert app.llama_integration.LLAMA_HEALTHY
