"""Cache utilities for middleware idempotency.

Provides a pluggable store interface with in-memory implementation
and Redis support for production use.
"""

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)

try:  # Optional dependency; provide a tiny fallback to avoid hard dep in tests
    from cachetools import TTLCache  # type: ignore
except Exception:  # pragma: no cover - fallback implementation
    from collections import OrderedDict

    class TTLCache:  # type: ignore
        def __init__(self, maxsize: int, ttl: float):
            self.maxsize = int(maxsize)
            self.ttl = float(ttl)
            self._data: dict[str, float] = {}
            self._order: OrderedDict[str, float] = OrderedDict()

        def _prune(self, now: float) -> None:
            # Remove expired entries
            expired = [k for k, ts in list(self._data.items()) if now - ts > self.ttl]
            for k in expired:
                self._data.pop(k, None)
                self._order.pop(k, None)
            # Enforce maxsize by evicting oldest
            while len(self._data) > self.maxsize and self._order:
                k, _ = self._order.popitem(last=False)
                self._data.pop(k, None)

        def get(self, key: str, default=None):
            now = time.monotonic()
            ts = self._data.get(key)
            if ts is None:
                return default
            if now - ts > self.ttl:
                # expired
                self._data.pop(key, None)
                self._order.pop(key, None)
                return default
            return ts

        def __setitem__(self, key: str, value: float) -> None:
            now = time.monotonic()
            self._data[key] = float(value)
            # maintain insertion order
            self._order.pop(key, None)
            self._order[key] = now
            self._prune(now)

        def __contains__(self, key: str) -> bool:  # pragma: no cover - convenience
            return self.get(key) is not None

        def __len__(self) -> int:  # pragma: no cover - convenience
            return len(self._data)


class IdempotencyEntry:
    """Represents a cached idempotency response."""

    def __init__(self, status_code: int, headers: dict[str, str], body: bytes):
        self.status_code = status_code
        self.headers = headers
        self.body = body
        self.created_at = time.monotonic()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "status_code": self.status_code,
            "headers": self.headers,
            "body": self.body.decode("utf-8", errors="replace"),
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "IdempotencyEntry":
        """Create from dictionary."""
        entry = cls(
            status_code=data["status_code"],
            headers=data["headers"],
            body=data["body"].encode("utf-8"),
        )
        entry.created_at = data["created_at"]
        return entry

    def is_expired(self, ttl: float) -> bool:
        """Check if this entry has expired."""
        return time.monotonic() - self.created_at > ttl


class IdempotencyStore(ABC):
    """Abstract base class for idempotency storage."""

    @abstractmethod
    async def get(self, key: str) -> IdempotencyEntry | None:
        """Retrieve cached response by key."""
        pass

    @abstractmethod
    async def set(self, key: str, entry: IdempotencyEntry, ttl: float) -> None:
        """Store response with TTL."""
        pass

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Delete cached response."""
        pass


class InMemoryIdempotencyStore(IdempotencyStore):
    """In-memory idempotency store using TTLCache."""

    def __init__(self, maxsize: int = 10000, ttl: float = 300.0):
        self._cache = TTLCache(maxsize=maxsize, ttl=ttl)
        self._data: dict[str, IdempotencyEntry] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> IdempotencyEntry | None:
        """Retrieve cached response by key."""
        async with self._lock:
            return self._data.get(key)

    async def set(self, key: str, entry: IdempotencyEntry, ttl: float) -> None:
        """Store response with TTL."""
        async with self._lock:
            self._data[key] = entry
            # Use the cache for TTL management
            self._cache[key] = time.monotonic()

            # Clean up expired entries
            now = time.monotonic()
            expired_keys = [
                k for k in self._data.keys()
                if k not in self._cache or self._data[k].is_expired(ttl)
            ]
            for k in expired_keys:
                del self._data[k]

    async def delete(self, key: str) -> None:
        """Delete cached response."""
        async with self._lock:
            self._data.pop(key, None)
            self._cache.__delitem__(key) if key in self._cache else None


# Global store instance - can be replaced with Redis in production
_idempotency_store: IdempotencyStore | None = None


def get_idempotency_store() -> IdempotencyStore:
    """Get the global idempotency store instance."""
    global _idempotency_store
    if _idempotency_store is None:
        # Initialize with default in-memory store
        import os
        maxsize = int(os.getenv("IDEMPOTENCY_CACHE_MAXSIZE", "10000"))
        ttl = float(os.getenv("IDEMPOTENCY_CACHE_TTL", "300"))  # 5 minutes default
        _idempotency_store = InMemoryIdempotencyStore(maxsize=maxsize, ttl=ttl)
        logger.info(f"Initialized idempotency store: maxsize={maxsize}, ttl={ttl}s")
    return _idempotency_store


def set_idempotency_store(store: IdempotencyStore) -> None:
    """Set the global idempotency store (for testing or Redis replacement)."""
    global _idempotency_store
    _idempotency_store = store
    logger.info(f"Set idempotency store to: {type(store).__name__}")


def make_idempotency_key(method: str, path: str, idempotency_key: str, user_id: str) -> str:
    """Create a stable cache key for idempotency.

    Key format: method:path:idempotency_key:user_id
    """
    # Normalize path to remove query parameters and trailing slashes
    clean_path = path.split("?")[0].rstrip("/")
    return f"{method}:{clean_path}:{idempotency_key}:{user_id}"
