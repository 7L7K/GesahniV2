import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest

from app.token_store import (
    LocalStorage,
    allow_refresh,
    claim_refresh_jti,
    claim_refresh_jti_with_retry,
    clear_local_storage,
    get_last_used_jti,
    get_storage_stats,
    has_redis,
    incr_login_counter,
    is_access_revoked,
    is_refresh_allowed,
    is_refresh_family_revoked,
    record_pat_last_used,
    revoke_access,
    revoke_refresh_family,
    set_last_used_jti,
    start_cleanup_task,
    stop_cleanup_task,
)


class TestLocalStorage:
    """Test the LocalStorage class with TTL and cleanup functionality."""
    
    def test_local_storage_set_get(self):
        """Test basic set and get operations."""
        storage = LocalStorage()
        storage.set("test_key", "test_value", 60)
        assert storage.get("test_key") == "test_value"
    
    def test_local_storage_ttl_expiration(self):
        """Test that entries expire after TTL."""
        storage = LocalStorage()
        storage.set("test_key", "test_value", 1)  # 1 second TTL
        assert storage.get("test_key") == "test_value"
        
        # Wait for expiration
        time.sleep(1.1)
        assert storage.get("test_key") is None
    
    def test_local_storage_exists(self):
        """Test exists method."""
        storage = LocalStorage()
        assert not storage.exists("test_key")
        
        storage.set("test_key", "test_value", 60)
        assert storage.exists("test_key")
        
        # Test expired key
        storage.set("expired_key", "value", 1)
        time.sleep(1.1)
        assert not storage.exists("expired_key")
    
    def test_local_storage_delete(self):
        """Test delete method."""
        storage = LocalStorage()
        storage.set("test_key", "test_value", 60)
        assert storage.exists("test_key")
        
        assert storage.delete("test_key") is True
        assert not storage.exists("test_key")
        assert storage.delete("nonexistent_key") is False
    
    def test_local_storage_cleanup(self):
        """Test automatic cleanup of expired entries."""
        storage = LocalStorage(cleanup_interval=1)  # 1 second cleanup interval
        
        # Add some entries with different TTLs
        storage.set("short", "value1", 1)
        storage.set("long", "value2", 10)
        
        # Force cleanup by calling _maybe_cleanup
        storage._maybe_cleanup()
        
        # Short entry should still exist
        assert storage.exists("short")
        assert storage.exists("long")
        
        # Wait for short entry to expire and trigger cleanup
        time.sleep(1.1)
        storage._maybe_cleanup()
        
        # Short entry should be cleaned up
        assert not storage.exists("short")
        assert storage.exists("long")
    
    def test_local_storage_thread_safety(self):
        """Test thread safety of LocalStorage."""
        import threading
        
        storage = LocalStorage()
        results = []
        
        def worker():
            for i in range(100):
                storage.set(f"key_{i}", f"value_{i}", 60)
                results.append(storage.get(f"key_{i}"))
        
        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # All operations should complete without errors
        assert len(results) == 500


class TestTokenStoreRedisFallback:
    """Test Redis fallback behavior when Redis is unavailable."""
    
    @pytest.fixture(autouse=True)
    async def setup(self):
        """Clear local storage before each test."""
        await clear_local_storage()
        yield
        await clear_local_storage()
    
    @pytest.mark.asyncio
    async def test_has_redis_with_redis_available(self):
        """Test has_redis when Redis is available."""
        with patch('app.token_store._get_redis') as mock_get_redis:
            mock_redis = AsyncMock()
            mock_redis.ping.return_value = True
            mock_get_redis.return_value = mock_redis
            
            result = await has_redis()
            assert result is True
            mock_redis.ping.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_has_redis_with_redis_unavailable(self):
        """Test has_redis when Redis is unavailable."""
        with patch('app.token_store._get_redis') as mock_get_redis:
            mock_get_redis.return_value = None
            
            result = await has_redis()
            assert result is False
    
    @pytest.mark.asyncio
    async def test_has_redis_with_redis_connection_error(self):
        """Test has_redis when Redis connection fails."""
        with patch('app.token_store._get_redis') as mock_get_redis:
            mock_redis = AsyncMock()
            mock_redis.ping.side_effect = Exception("Connection failed")
            mock_get_redis.return_value = mock_redis
            
            result = await has_redis()
            assert result is False
    
    @pytest.mark.asyncio
    async def test_allow_refresh_redis_fallback(self):
        """Test allow_refresh falls back to local storage when Redis fails."""
        with patch('app.token_store._get_redis') as mock_get_redis:
            mock_redis = AsyncMock()
            mock_redis.set.side_effect = Exception("Redis error")
            mock_redis.get.side_effect = Exception("Redis error")
            mock_get_redis.return_value = mock_redis
            
            await allow_refresh("test_sid", "test_jti", 60)
            
            # Should fall back to local storage
            result = await is_refresh_allowed("test_sid", "test_jti")
            assert result is True
    
    @pytest.mark.asyncio
    async def test_is_refresh_allowed_redis_fallback(self):
        """Test is_refresh_allowed falls back to local storage when Redis fails."""
        with patch('app.token_store._get_redis') as mock_get_redis:
            mock_redis = AsyncMock()
            mock_redis.get.side_effect = Exception("Redis error")
            mock_get_redis.return_value = mock_redis
            
            # First set a value in local storage
            await allow_refresh("test_sid", "test_jti", 60)
            
            # Should use local storage fallback
            result = await is_refresh_allowed("test_sid", "test_jti")
            assert result is True
    
    @pytest.mark.asyncio
    async def test_claim_refresh_jti_redis_fallback(self):
        """Test claim_refresh_jti falls back to local storage when Redis fails."""
        with patch('app.token_store._get_redis') as mock_get_redis:
            mock_redis = AsyncMock()
            mock_redis.set.side_effect = Exception("Redis error")
            mock_get_redis.return_value = mock_redis
            
            # First claim should succeed
            result1 = await claim_refresh_jti("test_sid", "test_jti", 60)
            assert result1 is True
            
            # Second claim should fail (already used)
            result2 = await claim_refresh_jti("test_sid", "test_jti", 60)
            assert result2 is False
    
    @pytest.mark.asyncio
    async def test_claim_refresh_jti_with_retry_redis_fallback(self):
        """Test claim_refresh_jti_with_retry falls back to local storage when Redis fails."""
        # Clear storage before test
        await clear_local_storage()
        
        with patch('app.token_store._get_redis') as mock_get_redis:
            mock_redis = AsyncMock()
            # Mock all Redis operations to fail, forcing fallback to local
            mock_redis.set.side_effect = Exception("Redis error")
            mock_redis.get.side_effect = Exception("Redis error")
            mock_redis.delete.side_effect = Exception("Redis error")
            mock_get_redis.return_value = mock_redis
            
            # First claim should succeed
            success1, error1 = await claim_refresh_jti_with_retry("test_sid", "test_jti", 60)
            assert success1 is True
            assert error1 is None
            
            # Second claim should fail (already used) - don't clear storage between calls
            success2, error2 = await claim_refresh_jti_with_retry("test_sid", "test_jti", 60)
            assert success2 is False
            assert error2 == "already_used"
    
    @pytest.mark.asyncio
    async def test_set_get_last_used_jti_redis_fallback(self):
        """Test set_last_used_jti and get_last_used_jti with Redis fallback."""
        with patch('app.token_store._get_redis') as mock_get_redis:
            mock_redis = AsyncMock()
            mock_redis.set.side_effect = Exception("Redis error")
            mock_redis.get.side_effect = Exception("Redis error")
            mock_get_redis.return_value = mock_redis
            
            await set_last_used_jti("test_sid", "test_jti", 60)
            result = await get_last_used_jti("test_sid")
            assert result == "test_jti"
    
    @pytest.mark.asyncio
    async def test_revoke_refresh_family_redis_fallback(self):
        """Test revoke_refresh_family and is_refresh_family_revoked with Redis fallback."""
        with patch('app.token_store._get_redis') as mock_get_redis:
            mock_redis = AsyncMock()
            mock_redis.set.side_effect = Exception("Redis error")
            mock_redis.get.side_effect = Exception("Redis error")
            mock_get_redis.return_value = mock_redis
            
            await revoke_refresh_family("test_sid", 60)
            result = await is_refresh_family_revoked("test_sid")
            assert result is True
    
    @pytest.mark.asyncio
    async def test_revoke_access_redis_fallback(self):
        """Test revoke_access and is_access_revoked with Redis fallback."""
        with patch('app.token_store._get_redis') as mock_get_redis:
            mock_redis = AsyncMock()
            mock_redis.set.side_effect = Exception("Redis error")
            mock_redis.get.side_effect = Exception("Redis error")
            mock_get_redis.return_value = mock_redis
            
            await revoke_access("test_jti", 60)
            result = await is_access_revoked("test_jti")
            assert result is True
    
    @pytest.mark.asyncio
    async def test_incr_login_counter_redis_fallback(self):
        """Test incr_login_counter with Redis fallback."""
        with patch('app.token_store._get_redis') as mock_get_redis:
            mock_redis = AsyncMock()
            mock_redis.pipeline.return_value.execute.side_effect = Exception("Redis error")
            mock_get_redis.return_value = mock_redis
            
            # First increment
            result1 = await incr_login_counter("test_key", 60)
            assert result1 == 1
            
            # Second increment
            result2 = await incr_login_counter("test_key", 60)
            assert result2 == 2
    
    @pytest.mark.asyncio
    async def test_record_pat_last_used_redis_fallback(self):
        """Test record_pat_last_used with Redis fallback."""
        with patch('app.token_store._get_redis') as mock_get_redis:
            mock_redis = AsyncMock()
            mock_redis.set.side_effect = Exception("Redis error")
            mock_get_redis.return_value = mock_redis
            
            await record_pat_last_used("test_pat_id", 60)
            # Should not raise any exceptions


class TestCleanupTask:
    """Test the background cleanup task functionality."""
    
    @pytest.mark.asyncio
    async def test_start_stop_cleanup_task(self):
        """Test starting and stopping the cleanup task."""
        # Start the cleanup task
        await start_cleanup_task()
        
        # Check that it's running
        stats = await get_storage_stats()
        assert stats["cleanup_task_running"] is True
        
        # Stop the cleanup task
        await stop_cleanup_task()
        
        # Check that it's stopped
        stats = await get_storage_stats()
        assert stats["cleanup_task_running"] is False
    
    @pytest.mark.asyncio
    async def test_cleanup_task_multiple_starts(self):
        """Test that multiple start calls don't create multiple tasks."""
        await start_cleanup_task()
        await start_cleanup_task()  # Should be no-op
        
        stats = await get_storage_stats()
        assert stats["cleanup_task_running"] is True
        
        await stop_cleanup_task()
    
    @pytest.mark.asyncio
    async def test_get_storage_stats(self):
        """Test get_storage_stats returns correct information."""
        # Add some test data
        await allow_refresh("test_sid", "test_jti", 60)
        await revoke_access("test_jti", 60)
        
        stats = await get_storage_stats()
        
        assert "redis_available" in stats
        assert "local_storage" in stats
        assert "cleanup_task_running" in stats
        
        local_storage = stats["local_storage"]
        assert "refresh_tokens" in local_storage
        assert "counters" in local_storage
        assert "last_used_jti" in local_storage
        assert "revoked_families" in local_storage
        assert "revoked_access" in local_storage
    
    @pytest.mark.asyncio
    async def test_clear_local_storage(self):
        """Test clear_local_storage clears all storage."""
        # Add some test data
        await allow_refresh("test_sid", "test_jti", 60)
        await revoke_access("test_jti", 60)
        
        # Verify data exists
        stats_before = await get_storage_stats()
        assert stats_before["local_storage"]["refresh_tokens"] > 0
        assert stats_before["local_storage"]["revoked_access"] > 0
        
        # Clear storage
        await clear_local_storage()
        
        # Verify data is cleared
        stats_after = await get_storage_stats()
        assert stats_after["local_storage"]["refresh_tokens"] == 0
        assert stats_after["local_storage"]["revoked_access"] == 0


class TestTokenStoreIntegration:
    """Integration tests for token store functionality."""
    
    @pytest.fixture(autouse=True)
    async def setup(self):
        """Clear local storage before each test."""
        await clear_local_storage()
        yield
        await clear_local_storage()
    
    @pytest.mark.asyncio
    async def test_refresh_token_rotation_flow(self):
        """Test complete refresh token rotation flow."""
        sid = "test_session"
        jti1 = "jti_1"
        jti2 = "jti_2"
        
        # Allow refresh for the session
        await allow_refresh(sid, jti1, 60)
        assert await is_refresh_allowed(sid, jti1) is True
        
        # Claim the first JTI
        assert await claim_refresh_jti(sid, jti1, 60) is True
        assert await claim_refresh_jti(sid, jti1, 60) is False  # Already used
        
        # Set last used JTI
        await set_last_used_jti(sid, jti1, 60)
        assert await get_last_used_jti(sid) == jti1
        
        # Allow refresh with new JTI
        await allow_refresh(sid, jti2, 60)
        assert await is_refresh_allowed(sid, jti2) is True
        assert await is_refresh_allowed(sid, jti1) is False  # Old JTI no longer allowed
    
    @pytest.mark.asyncio
    async def test_token_revocation_flow(self):
        """Test complete token revocation flow."""
        sid = "test_session"
        jti = "test_jti"
        
        # Revoke refresh family
        await revoke_refresh_family(sid, 60)
        assert await is_refresh_family_revoked(sid) is True
        
        # Revoke access token
        await revoke_access(jti, 60)
        assert await is_access_revoked(jti) is True
    
    @pytest.mark.asyncio
    async def test_rate_limiting_flow(self):
        """Test rate limiting functionality."""
        key = "test_rate_limit"
        
        # Increment counter multiple times
        assert await incr_login_counter(key, 60) == 1
        assert await incr_login_counter(key, 60) == 2
        assert await incr_login_counter(key, 60) == 3
    
    @pytest.mark.asyncio
    async def test_pat_last_used_tracking(self):
        """Test Personal Access Token last used tracking."""
        pat_id = "test_pat"
        
        await record_pat_last_used(pat_id, 60)
        # Should not raise any exceptions and store the timestamp


class TestTokenStoreErrorHandling:
    """Test error handling in token store operations."""
    
    @pytest.mark.asyncio
    async def test_redis_connection_failure_handling(self):
        """Test handling of Redis connection failures."""
        with patch('app.token_store._get_redis') as mock_get_redis:
            mock_get_redis.return_value = None  # Simulate Redis unavailable
            
            # All operations should gracefully fall back to local storage
            await allow_refresh("test_sid", "test_jti", 60)
            await revoke_access("test_jti", 60)
            await record_pat_last_used("test_pat", 60)
            
            # Should not raise exceptions
            assert True
    
    @pytest.mark.asyncio
    async def test_redis_operation_failure_handling(self):
        """Test handling of Redis operation failures."""
        with patch('app.token_store._get_redis') as mock_get_redis:
            mock_redis = AsyncMock()
            mock_redis.set.side_effect = Exception("Operation failed")
            mock_redis.get.side_effect = Exception("Operation failed")
            mock_redis.pipeline.return_value.execute.side_effect = Exception("Operation failed")
            mock_get_redis.return_value = mock_redis
            
            # All operations should gracefully fall back to local storage
            await allow_refresh("test_sid", "test_jti", 60)
            await is_refresh_allowed("test_sid", "test_jti")
            await claim_refresh_jti("test_sid", "test_jti", 60)
            await incr_login_counter("test_key", 60)
            
            # Should not raise exceptions
            assert True
    
    @pytest.mark.asyncio
    async def test_cleanup_task_error_handling(self):
        """Test that cleanup task continues running even if errors occur."""
        await start_cleanup_task()
        
        # Add some test data
        await allow_refresh("test_sid", "test_jti", 60)
        
        # Wait a bit for cleanup to run
        await asyncio.sleep(0.1)
        
        # Task should still be running
        stats = await get_storage_stats()
        assert stats["cleanup_task_running"] is True
        
        await stop_cleanup_task()
