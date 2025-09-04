import pytest
import logging
from unittest.mock import patch
from app.main import create_app

def test_ci_skips_rate_limit(caplog):
    """Test that CI mode correctly skips rate limiting by checking logs."""
    with caplog.at_level(logging.INFO):
        with patch.dict('os.environ', {'CI': '1'}):
            app = create_app()

    # Check that the logs show CI detection and rate limiting being skipped
    assert "CI detection: in_ci=True, rate_limit_enabled=False" in caplog.text
    assert "RateLimitMiddleware skipped (CI mode or disabled)" in caplog.text

def test_rate_limit_disabled_flag(caplog):
    """Test that RATE_LIMIT_ENABLED=0 correctly disables rate limiting by checking logs."""
    with caplog.at_level(logging.INFO):
        with patch.dict('os.environ', {'RATE_LIMIT_ENABLED': '0'}):
            app = create_app()

    # Check that the logs show rate limiting being disabled
    assert "RateLimitMiddleware skipped (CI mode or disabled)" in caplog.text
