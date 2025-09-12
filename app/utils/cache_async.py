from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any


class CachedError(RuntimeError):
    """Raised when a loader previously failed and the circuit is open."""


class AsyncTTLCache:
    """Simple async TTL memoization with per-key circuit breaker.

    - get(key, loader): returns cached value if fresh; otherwise awaits loader()
      and caches the result for `ttl_seconds`.
    - If loader raises, the error is swallowed by the caller by catching
      CachedError. A per-key open-circuit window prevents re-calling loader
      for the TTL duration after a failure.
    """

    def __init__(self, ttl_seconds: int = 5):
        self._ttl = max(1, int(ttl_seconds))
        self._cache: dict[Any, tuple[float, Any]] = {}
        self._error_until: dict[Any, float] = {}
        self._locks: dict[Any, asyncio.Lock] = {}

    def _lock_for(self, key: Any) -> asyncio.Lock:
        lock = self._locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[key] = lock
        return lock

    async def get(self, key: Any, loader: Callable[[], Awaitable[Any]]) -> Any:
        now = time.time()
        # Fast path: error circuit open
        until = self._error_until.get(key)
        if until and now < until:
            raise CachedError("circuit_open")

        # Fast path: fresh cache
        exp_val = self._cache.get(key)
        if exp_val is not None:
            exp, val = exp_val
            if now < exp:
                return val

        # Serialize per-key refreshes
        async with self._lock_for(key):
            # Re-check inside the lock
            now = time.time()
            until = self._error_until.get(key)
            if until and now < until:
                raise CachedError("circuit_open")
            exp_val = self._cache.get(key)
            if exp_val is not None:
                exp, val = exp_val
                if now < exp:
                    return val

            # Load fresh
            try:
                val = await loader()
            except Exception:
                # Open circuit for TTL duration
                self._error_until[key] = time.time() + self._ttl
                raise CachedError("loader_failed")

            # Cache and return
            self._cache[key] = (time.time() + self._ttl, val)
            # Reset error circuit on success
            self._error_until.pop(key, None)
            return val


__all__ = ["AsyncTTLCache", "CachedError"]

