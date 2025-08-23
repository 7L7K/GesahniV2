"""Unit tests for the race condition fix in refresh token rotation."""

from unittest.mock import AsyncMock, patch

import pytest

from app.token_store import claim_refresh_jti_with_retry


@pytest.mark.asyncio
async def test_claim_refresh_jti_with_retry_success():
    """Test successful JTI claim with retry mechanism."""
    with patch('app.token_store._get_redis') as mock_get_redis:
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis
        
        # Mock successful lock acquisition and JTI claim
        mock_redis.set.side_effect = [True, True]  # Lock acquired, JTI set
        mock_redis.get.return_value = None  # JTI not already used
        mock_redis.delete.return_value = 1  # Lock released
        
        success, error_reason = await claim_refresh_jti_with_retry("test_sid", "test_jti", 300)
        
        assert success is True
        assert error_reason is None
        assert mock_redis.set.call_count == 2  # Lock + JTI
        assert mock_redis.delete.call_count == 1  # Lock release


@pytest.mark.asyncio
async def test_claim_refresh_jti_with_retry_already_used():
    """Test JTI claim when token is already used."""
    with patch('app.token_store._get_redis') as mock_get_redis:
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis
        
        # Mock successful lock acquisition but JTI already used
        mock_redis.set.side_effect = [True, False]  # Lock acquired, JTI already set
        mock_redis.get.return_value = "1"  # JTI already used
        mock_redis.delete.return_value = 1  # Lock released
        
        success, error_reason = await claim_refresh_jti_with_retry("test_sid", "test_jti", 300)
        
        assert success is False
        assert error_reason == "already_used"
        # The function returns early when JTI is already used, so only lock is set
        assert mock_redis.set.call_count == 1  # Only lock attempt
        assert mock_redis.delete.call_count == 1  # Lock release


@pytest.mark.asyncio
async def test_claim_refresh_jti_with_retry_lock_timeout():
    """Test JTI claim when lock acquisition times out."""
    with patch('app.token_store._get_redis') as mock_get_redis:
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis
        
        # Mock failed lock acquisition after retries
        mock_redis.set.return_value = False  # Lock never acquired
        
        success, error_reason = await claim_refresh_jti_with_retry("test_sid", "test_jti", 300)
        
        assert success is False
        assert error_reason == "lock_timeout"
        # Should have tried to acquire lock multiple times (max_retries + 1)
        assert mock_redis.set.call_count >= 4  # Initial + 3 retries


@pytest.mark.asyncio
async def test_claim_refresh_jti_with_retry_redis_fallback():
    """Test JTI claim falls back to local storage when Redis fails."""
    with patch('app.token_store._get_redis') as mock_get_redis:
        mock_get_redis.return_value = None  # No Redis available
        
        # Clear local storage to ensure clean state
        from app.token_store import clear_local_storage
        await clear_local_storage()
        
        success, error_reason = await claim_refresh_jti_with_retry("test_sid", "test_jti", 300)
        
        assert success is True
        assert error_reason is None


@pytest.mark.asyncio
async def test_claim_refresh_jti_with_retry_redis_exception():
    """Test JTI claim falls back to local storage when Redis raises exception."""
    with patch('app.token_store._get_redis') as mock_get_redis:
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis
        
        # Mock Redis exception on lock acquisition
        mock_redis.set.side_effect = Exception("Redis connection failed")
        
        # Clear local storage to ensure clean state
        from app.token_store import clear_local_storage
        await clear_local_storage()
        
        success, error_reason = await claim_refresh_jti_with_retry("test_sid", "test_jti", 300)
        
        # Should fall back to local storage and succeed
        assert success is True
        assert error_reason is None


@pytest.mark.asyncio
async def test_claim_refresh_jti_with_retry_concurrent_simulation():
    """Test JTI claim behavior under simulated concurrent access."""
    with patch('app.token_store._get_redis') as mock_get_redis:
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis
        
        # Simulate first request getting lock, second request waiting
        lock_acquired = [False]  # Track if lock was acquired
        
        async def mock_set(key, value, ex=None, nx=False):
            if "lock" in key and nx:
                if not lock_acquired[0]:
                    lock_acquired[0] = True
                    return True
                else:
                    return False
            elif "refresh_used" in key and nx:
                return True  # JTI claim succeeds
            return True
        
        mock_redis.set.side_effect = mock_set
        mock_redis.get.return_value = None
        mock_redis.delete.return_value = 1
        
        # First request should succeed
        success1, error_reason1 = await claim_refresh_jti_with_retry("test_sid", "test_jti", 300)
        assert success1 is True
        assert error_reason1 is None
        
        # Reset for second request
        lock_acquired[0] = False
        
        # Second request should also succeed (different JTI)
        success2, error_reason2 = await claim_refresh_jti_with_retry("test_sid", "test_jti2", 300)
        assert success2 is True
        assert error_reason2 is None


@pytest.mark.asyncio
async def test_claim_refresh_jti_with_retry_same_jti_concurrent():
    """Test that the same JTI cannot be claimed twice concurrently."""
    with patch('app.token_store._get_redis') as mock_get_redis:
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis
        
        # First request: lock acquired, JTI set
        # Second request: lock acquired, but JTI already exists
        jti_used = [False]
        
        async def mock_set(key, value, ex=None, nx=False):
            if "lock" in key and nx:
                return True  # Lock always acquired
            elif "refresh_used" in key and nx:
                if not jti_used[0]:
                    jti_used[0] = True
                    return True  # First JTI claim succeeds
                else:
                    return False  # Second JTI claim fails
        
        async def mock_get(key):
            if "refresh_used" in key:
                return "1" if jti_used[0] else None
            return None
        
        mock_redis.set.side_effect = mock_set
        mock_redis.get.side_effect = mock_get
        mock_redis.delete.return_value = 1
        
        # First request should succeed
        success1, error_reason1 = await claim_refresh_jti_with_retry("test_sid", "test_jti", 300)
        assert success1 is True
        assert error_reason1 is None
        
        # Second request with same JTI should fail
        success2, error_reason2 = await claim_refresh_jti_with_retry("test_sid", "test_jti", 300)
        assert success2 is False
        assert error_reason2 == "already_used"
