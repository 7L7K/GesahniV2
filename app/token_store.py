from __future__ import annotations

import os
import asyncio
import time
import threading
from typing import Optional, Dict, Tuple, Any
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

# Global state for Redis client and cleanup task
_redis_client: Optional[object] = None
_cleanup_task: Optional[asyncio.Task] = None
_cleanup_running = False

# Local storage with better structure and TTL tracking
@dataclass
class LocalEntry:
    value: Any
    expires_at: float
    created_at: float

class LocalStorage:
    """Thread-safe local storage with automatic cleanup and TTL support."""
    
    def __init__(self, cleanup_interval: int = 300):  # 5 minutes default
        self._storage: Dict[str, LocalEntry] = {}
        self._lock = threading.RLock()
        self._cleanup_interval = cleanup_interval
        self._last_cleanup = time.time()
    
    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        """Set a key with TTL."""
        expires_at = time.time() + max(1, ttl_seconds)
        entry = LocalEntry(value=value, expires_at=expires_at, created_at=time.time())
        
        with self._lock:
            self._storage[key] = entry
            self._maybe_cleanup()
    
    def get(self, key: str) -> Any:
        """Get a key, returning None if expired or not found."""
        with self._lock:
            entry = self._storage.get(key)
            if entry is None:
                return None
            
            if time.time() > entry.expires_at:
                del self._storage[key]
                return None
            
            return entry.value
    
    def exists(self, key: str) -> bool:
        """Check if key exists and is not expired."""
        return self.get(key) is not None
    
    def delete(self, key: str) -> bool:
        """Delete a key, returns True if it existed."""
        with self._lock:
            return self._storage.pop(key, None) is not None
    
    def _maybe_cleanup(self) -> None:
        """Clean up expired entries if enough time has passed."""
        now = time.time()
        if now - self._last_cleanup < self._cleanup_interval:
            return
        
        self._last_cleanup = now
        expired_keys = []
        
        for key, entry in self._storage.items():
            if now > entry.expires_at:
                expired_keys.append(key)
        
        for key in expired_keys:
            self._storage.pop(key, None)
        
        if expired_keys:
            logger.debug(f"Cleaned up {len(expired_keys)} expired entries from local storage")

# Initialize local storage instances
_local_used_refresh = LocalStorage()
_local_counters = LocalStorage()
_local_last_used_jti = LocalStorage()
_local_revoked_families = LocalStorage()
_local_revoked_access = LocalStorage()

# Threading lock for operations that need coordination
try:
    _local_lock = threading.RLock()
except Exception:  # pragma: no cover - fallback
    class _Dummy:
        def __enter__(self):
            return None
        def __exit__(self, *a):
            return False
    _local_lock = _Dummy()


async def _get_redis():
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    url = os.getenv("REDIS_URL")
    if not url:
        return None
    try:
        import redis.asyncio as redis  # type: ignore
    except Exception:
        return None
    try:
        _redis_client = redis.from_url(url, encoding="utf-8", decode_responses=True)
        # Test the connection
        await _redis_client.ping()
        logger.info("Redis connection established successfully")
        return _redis_client
    except Exception as e:
        logger.warning(f"Failed to connect to Redis: {e}")
        _redis_client = None
        return None


async def has_redis() -> bool:
    """Check if Redis is available and working."""
    try:
        redis_client = await _get_redis()
        if redis_client is None:
            return False
        # Test the connection
        await redis_client.ping()
        return True
    except Exception as e:
        logger.debug(f"Redis health check failed: {e}")
        return False


async def start_cleanup_task() -> None:
    """Start the background cleanup task for local storage."""
    global _cleanup_task, _cleanup_running
    
    if _cleanup_running:
        return
    
    _cleanup_running = True
    
    async def cleanup_worker():
        """Background task to periodically clean up expired entries."""
        while _cleanup_running:
            try:
                # Clean up all local storage instances
                _local_used_refresh._maybe_cleanup()
                _local_counters._maybe_cleanup()
                _local_last_used_jti._maybe_cleanup()
                _local_revoked_families._maybe_cleanup()
                _local_revoked_access._maybe_cleanup()
                
                # Log memory usage for monitoring
                total_entries = (
                    len(_local_used_refresh._storage) +
                    len(_local_counters._storage) +
                    len(_local_last_used_jti._storage) +
                    len(_local_revoked_families._storage) +
                    len(_local_revoked_access._storage)
                )
                
                if total_entries > 1000:  # Log warning if too many entries
                    logger.warning(f"High local storage usage: {total_entries} total entries")
                elif total_entries > 100:  # Log info for moderate usage
                    logger.info(f"Local storage usage: {total_entries} total entries")
                
                await asyncio.sleep(60)  # Run every minute
                
            except Exception as e:
                logger.error(f"Error in cleanup task: {e}")
                await asyncio.sleep(60)  # Continue even if there's an error
    
    _cleanup_task = asyncio.create_task(cleanup_worker())
    logger.info("Started local storage cleanup task")


async def stop_cleanup_task() -> None:
    """Stop the background cleanup task."""
    global _cleanup_task, _cleanup_running
    
    _cleanup_running = False
    if _cleanup_task:
        _cleanup_task.cancel()
        try:
            await _cleanup_task
        except asyncio.CancelledError:
            pass
        _cleanup_task = None
    logger.info("Stopped local storage cleanup task")


# ------------------------- Refresh token rotation ----------------------------


def _key_refresh_allow(sid: str) -> str:
    return f"refresh_allow:{sid}"


def _key_revoked_refresh_family(sid: str) -> str:
    return f"revoked_refresh_family:{sid}"


async def allow_refresh(sid: str, jti: str, ttl_seconds: int) -> None:
    """Allow refresh token rotation for a session."""
    r = await _get_redis()
    if r is not None:
        try:
            await r.set(_key_refresh_allow(sid), jti, ex=max(1, int(ttl_seconds)))
            return
        except Exception as e:
            logger.warning(f"Redis allow_refresh failed, falling back to local: {e}")
    
    # Local fallback
    key = f"refresh_allow:{sid}"
    _local_used_refresh.set(key, jti, ttl_seconds)


async def is_refresh_allowed(sid: str, jti: str) -> bool:
    """Check if refresh token rotation is allowed for a session."""
    r = await _get_redis()
    if r is not None:
        try:
            cur = await r.get(_key_refresh_allow(sid))
            return cur is None or str(cur) == str(jti)
        except Exception as e:
            logger.warning(f"Redis is_refresh_allowed failed, falling back to local: {e}")
    
    # Local fallback
    key = f"refresh_allow:{sid}"
    stored_jti = _local_used_refresh.get(key)
    return stored_jti is None or str(stored_jti) == str(jti)


async def claim_refresh_jti(sid: str, jti: str, ttl_seconds: int) -> bool:
    """Atomically mark a refresh ``jti`` for ``sid`` as used.

    Returns True only for the first caller; subsequent calls until TTL expiry
    return False. Uses Redis when available; falls back to a process-local map.
    """
    key = f"refresh_used:{sid}:{jti}"
    r = await _get_redis()
    if r is not None:
        try:
            # SET key NX EX ttl → True only when not previously set
            ok = await r.set(key, "1", ex=max(1, int(ttl_seconds)), nx=True)
            return bool(ok)
        except Exception as e:
            logger.warning(f"Redis claim_refresh_jti failed, falling back to local: {e}")
    
    # Local fallback with thread-safe operation
    with _local_lock:
        if _local_used_refresh.exists(key):
            return False
        _local_used_refresh.set(key, "1", ttl_seconds)
        return True


async def claim_refresh_jti_with_retry(sid: str, jti: str, ttl_seconds: int, max_retries: int = 3) -> tuple[bool, str | None]:
    """Atomically mark a refresh ``jti`` for ``sid`` as used with retry logic for race conditions.
    
    Returns (success, error_reason) where success is True only for the first caller.
    Handles race conditions by implementing a distributed lock mechanism.
    """
    key = f"refresh_used:{sid}:{jti}"
    lock_key = f"refresh_lock:{sid}:{jti}"
    r = await _get_redis()
    
    if r is not None:
        try:
            # First, try to acquire a distributed lock to prevent race conditions
            lock_acquired = await r.set(lock_key, "1", ex=5, nx=True)  # 5 second lock
            if not lock_acquired:
                # Another request is processing this JTI, wait and retry
                for retry in range(max_retries):
                    await asyncio.sleep(0.1 * (retry + 1))  # Exponential backoff
                    lock_acquired = await r.set(lock_key, "1", ex=5, nx=True)
                    if lock_acquired:
                        break
                
                if not lock_acquired:
                    return False, "lock_timeout"
            
            try:
                # Check if JTI was already used while we were waiting for lock
                already_used = await r.get(key)
                if already_used:
                    return False, "already_used"
                
                # Set the JTI as used
                ok = await r.set(key, "1", ex=max(1, int(ttl_seconds)), nx=True)
                return bool(ok), None
            finally:
                # Always release the lock
                await r.delete(lock_key)
                
        except Exception as e:
            logger.warning(f"Redis claim_refresh_jti_with_retry failed, falling back to local: {e}")
    
    # Local fallback with thread-safe operation
    with _local_lock:
        if _local_used_refresh.exists(key):
            return False, "already_used"
        _local_used_refresh.set(key, "1", ttl_seconds)
        return True, None


async def set_last_used_jti(sid: str, jti: str, ttl_seconds: int | None = None) -> None:
    """Set the last used JTI for a session."""
    key = f"refresh_last_used:{sid}"
    r = await _get_redis()
    if r is not None:
        try:
            if ttl_seconds and ttl_seconds > 0:
                await r.set(key, jti, ex=int(ttl_seconds))
            else:
                await r.set(key, jti)
            return
        except Exception as e:
            logger.warning(f"Redis set_last_used_jti failed, falling back to local: {e}")
    
    # Local fallback
    if ttl_seconds and ttl_seconds > 0:
        _local_last_used_jti.set(key, jti, ttl_seconds)
    else:
        # For entries without TTL, use a very long TTL (1 year)
        _local_last_used_jti.set(key, jti, 365 * 24 * 3600)


async def get_last_used_jti(sid: str) -> str | None:
    """Get the last used JTI for a session."""
    key = f"refresh_last_used:{sid}"
    r = await _get_redis()
    if r is not None:
        try:
            val = await r.get(key)
            return str(val) if val is not None else None
        except Exception as e:
            logger.warning(f"Redis get_last_used_jti failed, falling back to local: {e}")
    
    # Local fallback
    val = _local_last_used_jti.get(key)
    return str(val) if val is not None else None


async def revoke_refresh_family(sid: str, ttl_seconds: int) -> None:
    """Revoke a refresh token family."""
    r = await _get_redis()
    if r is not None:
        try:
            await r.set(_key_revoked_refresh_family(sid), "1", ex=max(1, int(ttl_seconds)))
            return
        except Exception as e:
            logger.warning(f"Redis revoke_refresh_family failed, falling back to local: {e}")
    
    # Local fallback
    key = f"fam:{sid}"
    _local_revoked_families.set(key, "1", ttl_seconds)


async def is_refresh_family_revoked(sid: str) -> bool:
    """Check if a refresh token family is revoked."""
    r = await _get_redis()
    if r is not None:
        try:
            val = await r.get(_key_revoked_refresh_family(sid))
            return val is not None
        except Exception as e:
            logger.warning(f"Redis is_refresh_family_revoked failed, falling back to local: {e}")
    
    # Local fallback
    key = f"fam:{sid}"
    return _local_revoked_families.exists(key)


# ---------------------------- Access revocation ------------------------------


def _key_revoked_access(jti: str) -> str:
    return f"revoked_access:{jti}"


async def revoke_access(jti: str, ttl_seconds: int) -> None:
    """Revoke an access token."""
    r = await _get_redis()
    if r is not None:
        try:
            await r.set(_key_revoked_access(jti), "1", ex=max(1, int(ttl_seconds)))
            return
        except Exception as e:
            logger.warning(f"Redis revoke_access failed, falling back to local: {e}")
    
    # Local fallback
    _local_revoked_access.set(jti, "1", ttl_seconds)


async def is_access_revoked(jti: str) -> bool:
    """Check if an access token is revoked."""
    r = await _get_redis()
    if r is not None:
        try:
            val = await r.get(_key_revoked_access(jti))
            return val is not None
        except Exception as e:
            logger.warning(f"Redis is_access_revoked failed, falling back to local: {e}")
    
    # Local fallback
    return _local_revoked_access.exists(jti)


# ---------------------------- Login rate limits ------------------------------


def _key_login_ip(ip: str) -> str:
    return f"rl:login:ip:{ip}"


def _key_login_user(email: str) -> str:
    return f"rl:login:user:{email}"


async def incr_login_counter(key: str, ttl_seconds: int) -> int:
    """Increment a login counter with TTL."""
    r = await _get_redis()
    if r is not None:
        try:
            p = r.pipeline()
            p.incr(key)
            p.expire(key, max(1, int(ttl_seconds)))
            res = await p.execute()
            return int(res[0]) if isinstance(res, (list, tuple)) and res else 0
        except Exception as e:
            logger.warning(f"Redis incr_login_counter failed, falling back to local: {e}")
    
    # Local fallback with atomic increment
    with _local_lock:
        current_value = _local_counters.get(key)
        if current_value is None:
            new_count = 1
        else:
            new_count = int(current_value) + 1
        
        _local_counters.set(key, str(new_count), ttl_seconds)
        return new_count


async def record_pat_last_used(pat_id: str, ttl_seconds: int | None = None) -> None:
    """Record the last used time for a Personal Access Token."""
    r = await _get_redis()
    if r is not None:
        try:
            key = f"pat:last_used:{pat_id}"
            timestamp = str(int(asyncio.get_event_loop().time() * 1000))
            if ttl_seconds and ttl_seconds > 0:
                await r.set(key, timestamp, ex=int(ttl_seconds))
            else:
                await r.set(key, timestamp)
            return
        except Exception as e:
            logger.warning(f"Redis record_pat_last_used failed, falling back to local: {e}")
    
    # Local fallback
    key = f"pat:last_used:{pat_id}"
    timestamp = str(int(asyncio.get_event_loop().time() * 1000))
    if ttl_seconds and ttl_seconds > 0:
        _local_last_used_jti.set(key, timestamp, ttl_seconds)
    else:
        # For entries without TTL, use a very long TTL (1 year)
        _local_last_used_jti.set(key, timestamp, 365 * 24 * 3600)


# ---------------------------- Health and monitoring --------------------------


async def get_storage_stats() -> dict:
    """Get statistics about local storage usage."""
    return {
        "redis_available": await has_redis(),
        "local_storage": {
            "refresh_tokens": len(_local_used_refresh._storage),
            "counters": len(_local_counters._storage),
            "last_used_jti": len(_local_last_used_jti._storage),
            "revoked_families": len(_local_revoked_families._storage),
            "revoked_access": len(_local_revoked_access._storage),
        },
        "cleanup_task_running": _cleanup_running,
    }


async def clear_local_storage() -> None:
    """Clear all local storage (useful for testing)."""
    with _local_lock:
        _local_used_refresh._storage.clear()
        _local_counters._storage.clear()
        _local_last_used_jti._storage.clear()
        _local_revoked_families._storage.clear()
        _local_revoked_access._storage.clear()
    logger.info("Cleared all local storage")


__all__ = [
    "allow_refresh",
    "is_refresh_allowed",
    "claim_refresh_jti",
    "claim_refresh_jti_with_retry",
    "set_last_used_jti",
    "get_last_used_jti",
    "revoke_refresh_family",
    "is_refresh_family_revoked",
    "revoke_access",
    "is_access_revoked",
    "_key_login_ip",
    "_key_login_user",
    "incr_login_counter",
    "record_pat_last_used",
    "start_cleanup_task",
    "stop_cleanup_task",
    "get_storage_stats",
    "clear_local_storage",
    "has_redis",
]


