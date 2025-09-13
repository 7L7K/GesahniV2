"""
Async-safe LRU Cache for idempotency.

Uses OrderedDict with asyncio.Lock for thread-safe operations.
TTL-based expiration with automatic cleanup.
"""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from typing import Any, TypeVar

T = TypeVar("T")


class AsyncLRUCache:
    """Async-safe LRU cache with TTL expiration.

    Thread-safe using asyncio.Lock. Automatic cleanup of expired entries.
    """

    def __init__(self, max_size: int = 1000, ttl_seconds: int = 300):
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._cache: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._lock = asyncio.Lock()
        self._cleanup_interval = min(ttl_seconds // 2, 60)  # Cleanup every half TTL or 60s
        self._cleanup_task: asyncio.Task | None = None

    async def start_cleanup_task(self):
        """Start background cleanup task."""
        async with self._lock:
            if self._cleanup_task is None:
                self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def stop_cleanup_task(self):
        """Stop background cleanup task."""
        async with self._lock:
            if self._cleanup_task:
                self._cleanup_task.cancel()
                try:
                    await self._cleanup_task
                except asyncio.CancelledError:
                    pass

    async def put(self, key: str, value: Any) -> None:
        """Store a value with automatic TTL."""
        async with self._lock:
            now = time.time()
            exp_time = now + self.ttl_seconds

            # Remove if exists to update LRU order
            self._cache.pop(key, None)

            # Add to cache
            self._cache[key] = (exp_time, value)

            # Evict if over max size
            while len(self._cache) > self.max_size:
                self._cache.popitem(last=False)  # Remove oldest (LRU)

    async def get(self, key: str) -> Any | None:
        """Retrieve a value, None if not found or expired."""
        async with self._lock:
            now = time.time()
            exp_val = self._cache.get(key)

            if exp_val is None:
                return None

            exp_time, value = exp_val
            if now > exp_time:
                # Expired, remove it
                del self._cache[key]
                return None

            # Move to end (most recently used)
            self._cache.move_to_end(key)
            return value

    async def _cleanup_loop(self):
        """Background task to clean up expired entries."""
        while True:
            try:
                await asyncio.sleep(self._cleanup_interval)
                await self._cleanup_expired()
            except asyncio.CancelledError:
                break
            except Exception:
                # Log but don't crash
                pass

    async def _cleanup_expired(self):
        """Remove expired entries."""
        async with self._lock:
            now = time.time()
            expired_keys = [
                key for key, (exp_time, _) in self._cache.items()
                if now > exp_time
            ]
            for key in expired_keys:
                del self._cache[key]


# Global idempotency cache for WebSocket requests
ws_idempotency_cache = AsyncLRUCache(max_size=10000, ttl_seconds=300)  # 5 min TTL


async def init_ws_idempotency_cache():
    """Initialize the WebSocket idempotency cache."""
    await ws_idempotency_cache.start_cleanup_task()


__all__ = ["AsyncLRUCache", "ws_idempotency_cache", "init_ws_idempotency_cache"]
