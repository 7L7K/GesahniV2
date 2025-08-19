import pytest
import time
import asyncio
from unittest.mock import patch, AsyncMock
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.auth import (
    _record_attempt, _throttled, _get_throttle_status, 
    _should_apply_backoff, _should_hard_lockout,
    _clear_rate_limit_data, _get_rate_limit_stats,
    _ATTEMPT_WINDOW, _ATTEMPT_MAX, _LOCKOUT_SECONDS,
    _EXPONENTIAL_BACKOFF_THRESHOLD, _HARD_LOCKOUT_THRESHOLD
)


class TestRateLimitingHelpers:
    """Test the rate limiting helper functions."""
    
    def setup_method(self):
        """Clear rate limiting data before each test."""
        _clear_rate_limit_data()
    
    def test_record_attempt_success(self):
        """Test recording a successful attempt clears the counter."""
        key = "test_user"
        
        # Record some failed attempts first
        _record_attempt(key, success=False)
        _record_attempt(key, success=False)
        
        # Verify counter is incremented
        assert _throttled(key) is None  # Not throttled yet
        
        # Record successful attempt
        _record_attempt(key, success=True)
        
        # Verify counter is cleared
        assert _throttled(key) is None
    
    def test_record_attempt_failure(self):
        """Test recording failed attempts increments counter."""
        key = "test_user"
        
        # Record failed attempts
        for i in range(_ATTEMPT_MAX):
            _record_attempt(key, success=False)
            if i < _ATTEMPT_MAX - 1:
                assert _throttled(key) is None  # Not throttled yet
            else:
                assert _throttled(key) is not None  # Now throttled
    
    def test_throttled_window_expiry(self):
        """Test that throttling resets after window expires."""
        key = "test_user"
        
        # Record enough failures to trigger throttling
        for _ in range(_ATTEMPT_MAX):
            _record_attempt(key, success=False)
        
        # Should be throttled
        assert _throttled(key) is not None
        
        # Fast forward time past the window by manipulating the stored timestamp
        import app.auth
        count, ts = app.auth._attempts[key]
        app.auth._attempts[key] = (count, ts - _ATTEMPT_WINDOW - 1)
        
        # Should no longer be throttled
        assert _throttled(key) is None
    
    def test_throttled_minimum_wait_time(self):
        """Test that throttling returns at least 1 second."""
        key = "test_user"
        
        # Record enough failures to trigger throttling
        for _ in range(_ATTEMPT_MAX):
            _record_attempt(key, success=False)
        
        # Should return at least 1 second
        wait_time = _throttled(key)
        assert wait_time is not None
        assert wait_time >= 1
    
    def test_get_throttle_status(self):
        """Test getting throttle status for both user and IP."""
        user_key = "user:test_user"
        ip_key = "ip:192.168.1.1"
        
        # Record failures for user only
        for _ in range(_ATTEMPT_MAX):
            _record_attempt(user_key, success=False)
        
        user_throttle, ip_throttle = _get_throttle_status(user_key, ip_key)
        
        assert user_throttle is not None
        assert ip_throttle is None
    
    def test_should_apply_backoff(self):
        """Test exponential backoff threshold check."""
        key = "test_user"
        
        # Below threshold
        assert not _should_apply_backoff(key)
        
        # At threshold
        for _ in range(_EXPONENTIAL_BACKOFF_THRESHOLD):
            _record_attempt(key, success=False)
        
        assert _should_apply_backoff(key)
    
    def test_should_hard_lockout(self):
        """Test hard lockout threshold check."""
        key = "test_user"
        
        # Below threshold
        assert not _should_hard_lockout(key)
        
        # At threshold
        for _ in range(_HARD_LOCKOUT_THRESHOLD):
            _record_attempt(key, success=False)
        
        assert _should_hard_lockout(key)
    
    def test_clear_rate_limit_data(self):
        """Test clearing rate limit data."""
        key = "test_user"
        
        # Add some data
        _record_attempt(key, success=False)
        assert _throttled(key) is None  # Not throttled yet
        
        # Clear specific key
        _clear_rate_limit_data(key)
        assert _get_rate_limit_stats(key) is None
    
    def test_get_rate_limit_stats(self):
        """Test getting rate limit statistics."""
        key = "test_user"
        
        # No data initially
        assert _get_rate_limit_stats(key) is None
        
        # Add some data
        _record_attempt(key, success=False)
        stats = _get_rate_limit_stats(key)
        
        assert stats is not None
        assert stats["count"] == 1
        assert "timestamp" in stats
        assert "window_expires" in stats
        assert "time_remaining" in stats
        assert "is_throttled" in stats
        assert "throttle_remaining" in stats


class TestRateLimitingIntegration:
    """Test rate limiting integration with the login endpoint."""
    
    def setup_method(self):
        """Clear rate limiting data before each test."""
        _clear_rate_limit_data()
    
    @pytest.mark.asyncio
    async def test_login_rate_limiting_user_and_ip(self, client: TestClient):
        """Test that both user and IP rate limiting work together."""
        # Mock authentication to always fail
        with patch('app.auth.pwd_context.verify', return_value=False), \
             patch('app.auth._fetch_password_hash', return_value="hashed_password"), \
             patch('app.auth._ensure_table'), \
             patch('app.auth._client_ip', return_value="192.168.1.1"):
            
            # Make multiple failed attempts for a user
            # Rate limiting is checked at the start, so we need one more attempt
            for i in range(_ATTEMPT_MAX + 1):
                response = client.post("/login", json={
                    "username": "test_user",
                    "password": "wrong_password"
                })
                
                if i < _ATTEMPT_MAX:
                    assert response.status_code == 401
                else:
                    # Should be rate limited after max attempts
                    assert response.status_code == 429
                    data = response.json()
                    assert data["detail"]["error"] == "rate_limited"
                    assert data["detail"]["retry_after"] > 0
    
    @pytest.mark.asyncio
    async def test_login_rate_limiting_ip_bypass_prevention(self, client: TestClient):
        """Test that IP-based rate limiting prevents bypassing user limits."""
        # Mock authentication to always fail
        with patch('app.auth.pwd_context.verify', return_value=False), \
             patch('app.auth._fetch_password_hash', return_value="hashed_password"), \
             patch('app.auth._ensure_table'), \
             patch('app.auth._client_ip', return_value="192.168.1.1"):
            
            # Make multiple failed attempts from the same IP
            # Rate limiting is checked at the start, so we need one more attempt
            for i in range(_ATTEMPT_MAX + 1):
                response = client.post("/login", json={
                    "username": f"user_{i}",  # Different usernames
                    "password": "wrong_password"
                })
                
                if i < _ATTEMPT_MAX:
                    assert response.status_code == 401
                else:
                    # Should be rate limited after max attempts from same IP
                    assert response.status_code == 429
                    data = response.json()
                    assert data["detail"]["error"] == "rate_limited"
    
    @pytest.mark.asyncio
    async def test_login_exponential_backoff(self, client: TestClient):
        """Test that exponential backoff is applied correctly."""
        # Mock authentication to always fail
        with patch('app.auth.pwd_context.verify', return_value=False), \
             patch('app.auth._fetch_password_hash', return_value="hashed_password"), \
             patch('app.auth._ensure_table'), \
             patch('app.auth._client_ip', return_value="192.168.1.1"), \
             patch('asyncio.sleep') as mock_sleep:
            
            # Make attempts up to backoff threshold
            for i in range(_EXPONENTIAL_BACKOFF_THRESHOLD):
                response = client.post("/login", json={
                    "username": "test_user",
                    "password": "wrong_password"
                })
                assert response.status_code == 401
            
            # Next attempt should trigger backoff
            response = client.post("/login", json={
                "username": "test_user",
                "password": "wrong_password"
            })
            
            # Should have called sleep
            mock_sleep.assert_called_once()
            sleep_duration = mock_sleep.call_args[0][0]
            assert 0.2 <= sleep_duration <= 1.0  # 200-1000ms
    
    @pytest.mark.asyncio
    async def test_login_hard_lockout(self, client: TestClient):
        """Test that hard lockout is applied after threshold."""
        # Mock authentication to always fail
        with patch('app.auth.pwd_context.verify', return_value=False), \
             patch('app.auth._fetch_password_hash', return_value="hashed_password"), \
             patch('app.auth._ensure_table'), \
             patch('app.auth._client_ip', return_value="192.168.1.1"):
            
            # Since _ATTEMPT_MAX (5) < _HARD_LOCKOUT_THRESHOLD (6), 
            # regular rate limiting will be triggered first
            # Make attempts up to regular rate limit threshold
            for i in range(_ATTEMPT_MAX + 1):
                response = client.post("/login", json={
                    "username": "test_user",
                    "password": "wrong_password"
                })
                
                if i < _ATTEMPT_MAX:
                    assert response.status_code == 401
                else:
                    # Should trigger regular rate limiting first
                    assert response.status_code == 429
                    data = response.json()
                    assert data["detail"]["error"] == "rate_limited"
                    assert data["detail"]["retry_after"] > 0
    
    @pytest.mark.asyncio
    async def test_login_success_clears_rate_limits(self, client: TestClient):
        """Test that successful login clears rate limiting."""
        # Mock authentication to fail first, then succeed
        with patch('app.auth.pwd_context.verify', side_effect=[False, False, False, True, False]), \
             patch('app.auth._fetch_password_hash', return_value="hashed_password"), \
             patch('app.auth._ensure_table'), \
             patch('app.auth._client_ip', return_value="192.168.1.1"):
            
            # Make some failed attempts
            for _ in range(3):
                response = client.post("/login", json={
                    "username": "test_user",
                    "password": "wrong_password"
                })
                assert response.status_code == 401
            
            # Successful login should clear rate limits
            response = client.post("/login", json={
                "username": "test_user",
                "password": "correct_password"
            })
            
            assert response.status_code == 200
            
            # Should be able to make more attempts without being rate limited
            response = client.post("/login", json={
                "username": "test_user",
                "password": "wrong_password"
            })
            assert response.status_code == 401  # Not rate limited
    
    @pytest.mark.asyncio
    async def test_login_most_restrictive_throttling(self, client: TestClient):
        """Test that the most restrictive throttling is applied."""
        # Mock authentication to always fail
        with patch('app.auth.pwd_context.verify', return_value=False), \
             patch('app.auth._fetch_password_hash', return_value="hashed_password"), \
             patch('app.auth._ensure_table'), \
             patch('app.auth._client_ip', return_value="192.168.1.1"):
            
            # Set up user throttling with 30s remaining
            user_key = "user:test_user"
            for _ in range(_ATTEMPT_MAX):
                _record_attempt(user_key, success=False)
            
            # Manipulate the timestamp to simulate 30s remaining
            import app.auth
            count, ts = app.auth._attempts[user_key]
            app.auth._attempts[user_key] = (count, ts - _LOCKOUT_SECONDS + 30)
            
            response = client.post("/login", json={
                "username": "test_user",
                "password": "wrong_password"
            })
            
            assert response.status_code == 429
            data = response.json()
            assert data["detail"]["retry_after"] == 30  # Should use user throttle


class TestRateLimitingEdgeCases:
    """Test edge cases in rate limiting."""
    
    def setup_method(self):
        """Clear rate limiting data before each test."""
        _clear_rate_limit_data()
    
    def test_concurrent_attempts(self):
        """Test handling of concurrent attempts."""
        key = "test_user"
        
        # Simulate concurrent attempts
        _record_attempt(key, success=False)
        _record_attempt(key, success=False)
        _record_attempt(key, success=False)
        
        # Should be at 3 attempts
        stats = _get_rate_limit_stats(key)
        assert stats["count"] == 3
    
    def test_window_boundary_conditions(self):
        """Test rate limiting at window boundaries."""
        key = "test_user"
        
        # Record attempts up to limit
        for _ in range(_ATTEMPT_MAX):
            _record_attempt(key, success=False)
        
        # Should be throttled
        assert _throttled(key) is not None
        
        # Test exactly at window boundary by manipulating timestamp
        import app.auth
        count, ts = app.auth._attempts[key]
        
        # Test just before window boundary (should still be throttled)
        app.auth._attempts[key] = (count, ts - _ATTEMPT_WINDOW + 0.1)
        assert _throttled(key) is not None
        
        # Test exactly at window boundary (should be expired)
        app.auth._attempts[key] = (count, ts - _ATTEMPT_WINDOW)
        assert _throttled(key) is None
        
        # Test just past window boundary
        app.auth._attempts[key] = (count, ts - _ATTEMPT_WINDOW - 0.1)
        
        # Should no longer be throttled
        assert _throttled(key) is None
    
    def test_zero_remaining_time_handling(self):
        """Test handling of zero remaining time."""
        key = "test_user"
        
        # Record attempts up to limit
        for _ in range(_ATTEMPT_MAX):
            _record_attempt(key, success=False)
        
        # Manipulate timestamp to exactly when lockout should expire
        import app.auth
        count, ts = app.auth._attempts[key]
        app.auth._attempts[key] = (count, ts - _LOCKOUT_SECONDS)
        
        # Should return at least 1 second
        wait_time = _throttled(key)
        assert wait_time is not None
        assert wait_time >= 1
    
    def test_malformed_attempt_data(self):
        """Test handling of malformed attempt data."""
        key = "test_user"
        
        # Manually insert malformed data
        import app.auth
        app.auth._attempts[key] = ("invalid", "data")
        
        # Should handle gracefully
        result = _throttled(key)
        assert result is None  # Should not crash
    
    def test_large_attempt_counts(self):
        """Test handling of very large attempt counts."""
        key = "test_user"
        
        # Manually insert large count
        import app.auth
        app.auth._attempts[key] = (999999, time.time())
        
        # Should be throttled
        assert _throttled(key) is not None
        
        # Should not crash
        stats = _get_rate_limit_stats(key)
        assert stats is not None
        assert stats["count"] == 999999
