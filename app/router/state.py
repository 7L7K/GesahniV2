from __future__ import annotations

import asyncio
import hashlib
import re
import time
from collections import OrderedDict
from typing import Any

from .config import CONFIG


class AsyncCachedHealth:
    """Async health snapshot cache with TTL-based lazy refresh.

    - get_snapshot(): returns last known snapshot immediately (may be stale).
      If the snapshot is stale and no refresh is running, it schedules a
      background refresh with asyncio.create_task().
    - refresh(): performs vendor health probes and updates the snapshot.
    """

    def __init__(self, *, ttl_seconds: float = 3.0) -> None:
        self._ttl = float(ttl_seconds)
        self._snapshot: dict[str, Any] = {"openai": {"ok": False, "latency_ms": 0}, "llama": {"ok": False, "latency_ms": 0}, "ts": 0.0}
        self._ts: float = 0.0
        self._task: asyncio.Task | None = None

    def get_snapshot(self) -> dict[str, Any]:
        now = time.monotonic()
        # Return current snapshot immediately
        snap = dict(self._snapshot)
        # Fire-and-forget refresh if stale and not already refreshing
        if now - self._ts > self._ttl and (self._task is None or self._task.done()):
            try:
                loop = asyncio.get_running_loop()
                self._task = loop.create_task(self.refresh())
            except RuntimeError:
                # No running loop (rare in request path); return stale data
                pass
        return snap

    async def refresh(self) -> None:
        # Perform vendor probes concurrently; tolerate failures
        try:
            from app.health import check_ollama_health, check_openai_health

            async def _probe(fn):
                try:
                    res = await fn(cache_result=True)
                    # The health module returns objects with attributes; map defensively
                    ok = bool(getattr(res, "healthy", False))
                    lat = int(getattr(res, "latency_ms", 0) or 0)
                    return ok, lat
                except Exception:
                    return False, 0

            openai_ok, openai_lat = await _probe(check_openai_health)
            llama_ok, llama_lat = await _probe(check_ollama_health)

            snap = {
                "openai": {"ok": openai_ok, "latency_ms": openai_lat},
                "llama": {"ok": llama_ok, "latency_ms": llama_lat},
                "ts": time.monotonic(),
            }

            # Update snapshot
            self._snapshot = snap
            self._ts = snap["ts"]
        except Exception:
            # On failure, keep previous snapshot; don't raise
            self._ts = time.monotonic()


# Module-level singleton with a 3s TTL
HEALTH = AsyncCachedHealth(ttl_seconds=3.0)


class TTLCache:
    """Simple in-process TTL+LRU cache.

    - max_entries: maximum number of entries to keep
    - ttl_seconds: time-to-live per entry
    """

    def __init__(self, *, max_entries: int, ttl_seconds: float) -> None:
        self._max = int(max_entries)
        self._ttl = float(ttl_seconds)
        # OrderedDict: key -> (expires_at, value)
        self._data: OrderedDict[str, tuple[float, Any]] = OrderedDict()

    def _purge_expired(self) -> None:
        now = time.monotonic()
        to_delete = []
        for k, (exp, _) in self._data.items():
            if exp < now:
                to_delete.append(k)
        for k in to_delete:
            self._data.pop(k, None)

    def get(self, key: str) -> Any | None:
        self._purge_expired()
        item = self._data.get(key)
        if not item:
            return None
        exp, val = item
        if exp < time.monotonic():
            self._data.pop(key, None)
            return None
        # Move to end (most recently used)
        self._data.move_to_end(key)
        return val

    def set(self, key: str, value: Any) -> None:
        self._purge_expired()
        # Evict while exceeding capacity (by access order - oldest first)
        while len(self._data) >= self._max and self._data:
            self._data.popitem(last=False)
        exp = time.monotonic() + self._ttl
        self._data[key] = (exp, value)
        self._data.move_to_end(key)


def _normalize_text(text: str) -> str:
    # Collapse whitespace and lowercase
    return re.sub(r"\s+", " ", text or "").strip().lower()


def _policy_hash() -> str:
    # Build a stable string from allowlists + default model + budget
    allow = ",".join(CONFIG.allowlist_models) if CONFIG.allowlist_models else ""
    default = CONFIG.router_default_model
    budget = str(CONFIG.router_budget_ms)
    base = f"allow:{allow}|d:{default}|b:{budget}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:10]


def make_semantic_cache_key(*, user_id: str, prompt_text: str) -> str:
    skills_ver = CONFIG.skills_version
    return f"uid:{user_id}|p:{_normalize_text(prompt_text)}|pol:{_policy_hash()}|sv:{skills_ver}"


def ensure_usage_ints(usage: dict[str, Any]) -> None:
    # Normalize usage keys to ints; accept multiple shapes
    ti = usage.get("tokens_in")
    to = usage.get("tokens_out")
    if ti is None:
        ti = usage.get("input_tokens", 0)
    if to is None:
        to = usage.get("output_tokens", 0)
    usage["tokens_in"] = int(ti or 0)
    usage["tokens_out"] = int(to or 0)


# Env-configured cache limits
_MAX_ENTRIES = int(CONFIG.cache_max_entries)
_TTL_S = float(CONFIG.cache_ttl_s)

# Exported semantic cache singleton
SEM_CACHE = TTLCache(max_entries=_MAX_ENTRIES, ttl_seconds=_TTL_S)
