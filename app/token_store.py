from __future__ import annotations

import os
import asyncio
from typing import Optional


_redis_client: Optional[object] = None
_local_used_refresh: dict[str, float] = {}
_local_counters: dict[str, tuple[int, float]] = {}
_local_last_used_jti: dict[str, str] = {}
_local_revoked_families: dict[str, float] = {}
try:
    import threading as _threading  # type: ignore
    _local_lock = _threading.Lock()
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
async def has_redis() -> bool:
    try:
        return (await _get_redis()) is not None
    except Exception:
        return False

    try:
        import redis.asyncio as redis  # type: ignore
    except Exception:
        return None
    try:
        _redis_client = redis.from_url(url, encoding="utf-8", decode_responses=True)
        return _redis_client
    except Exception:
        return None


# ------------------------- Refresh token rotation ----------------------------


def _key_refresh_allow(sid: str) -> str:
    return f"refresh_allow:{sid}"


def _key_revoked_refresh_family(sid: str) -> str:
    return f"revoked_refresh_family:{sid}"


async def allow_refresh(sid: str, jti: str, ttl_seconds: int) -> None:
    r = await _get_redis()
    if r is None:
        return
    try:
        await r.set(_key_refresh_allow(sid), jti, ex=max(1, int(ttl_seconds)))  # type: ignore[attr-defined]
    except Exception:
        pass


async def is_refresh_allowed(sid: str, jti: str) -> bool:
    r = await _get_redis()
    if r is None:
        return True
    try:
        cur = await r.get(_key_refresh_allow(sid))  # type: ignore[attr-defined]
        return cur is None or str(cur) == str(jti)
    except Exception:
        return True


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
            ok = await r.set(key, "1", ex=max(1, int(ttl_seconds)), nx=True)  # type: ignore[attr-defined]
            return bool(ok)
        except Exception:
            # fall back to local
            pass
    # Local fallback with coarse pruning
    import time as _time
    now = _time.time()
    with _local_lock:
        # prune expired
        try:
            for k, exp in list(_local_used_refresh.items()):
                if exp <= now:
                    _local_used_refresh.pop(k, None)
        except Exception:
            pass
        if key in _local_used_refresh:
            return False
        _local_used_refresh[key] = now + max(1, int(ttl_seconds))
        return True


async def set_last_used_jti(sid: str, jti: str, ttl_seconds: int | None = None) -> None:
    key = f"refresh_last_used:{sid}"
    r = await _get_redis()
    if r is not None:
        try:
            if ttl_seconds and ttl_seconds > 0:
                await r.set(key, jti, ex=int(ttl_seconds))  # type: ignore[attr-defined]
            else:
                await r.set(key, jti)  # type: ignore[attr-defined]
            return
        except Exception:
            pass
    with _local_lock:
        _local_last_used_jti[key] = jti


async def get_last_used_jti(sid: str) -> str | None:
    key = f"refresh_last_used:{sid}"
    r = await _get_redis()
    if r is not None:
        try:
            val = await r.get(key)  # type: ignore[attr-defined]
            return str(val) if val is not None else None
        except Exception:
            pass
    with _local_lock:
        return _local_last_used_jti.get(key)


async def revoke_refresh_family(sid: str, ttl_seconds: int) -> None:
    r = await _get_redis()
    if r is None:
        # Local fallback
        import time as _time
        with _local_lock:
            _local_revoked_families[f"fam:{sid}"] = _time.time() + max(1, int(ttl_seconds))
        return
    try:
        await r.set(_key_revoked_refresh_family(sid), "1", ex=max(1, int(ttl_seconds)))  # type: ignore[attr-defined]
    except Exception:
        pass


async def is_refresh_family_revoked(sid: str) -> bool:
    r = await _get_redis()
    if r is None:
        # Local fallback check with pruning
        import time as _time
        now = _time.time()
        key = f"fam:{sid}"
        with _local_lock:
            try:
                for k, exp in list(_local_revoked_families.items()):
                    if exp <= now:
                        _local_revoked_families.pop(k, None)
            except Exception:
                pass
            return key in _local_revoked_families
    try:
        val = await r.get(_key_revoked_refresh_family(sid))  # type: ignore[attr-defined]
        return val is not None
    except Exception:
        return False


# ---------------------------- Access revocation ------------------------------


def _key_revoked_access(jti: str) -> str:
    return f"revoked_access:{jti}"


async def revoke_access(jti: str, ttl_seconds: int) -> None:
    r = await _get_redis()
    if r is None:
        return
    try:
        await r.set(_key_revoked_access(jti), "1", ex=max(1, int(ttl_seconds)))  # type: ignore[attr-defined]
    except Exception:
        pass


async def is_access_revoked(jti: str) -> bool:
    r = await _get_redis()
    if r is None:
        return False
    try:
        val = await r.get(_key_revoked_access(jti))  # type: ignore[attr-defined]
        return val is not None
    except Exception:
        return False


# ---------------------------- Login rate limits ------------------------------


def _key_login_ip(ip: str) -> str:
    return f"rl:login:ip:{ip}"


def _key_login_user(email: str) -> str:
    return f"rl:login:user:{email}"


async def incr_login_counter(key: str, ttl_seconds: int) -> int:
    r = await _get_redis()
    if r is None:
        # Local fallback counter with TTL
        import time as _time
        now = _time.time()
        with _local_lock:
            # prune expired entries
            try:
                for k, (cnt, exp) in list(_local_counters.items()):
                    if exp <= now:
                        _local_counters.pop(k, None)
            except Exception:
                pass
            cnt, exp = _local_counters.get(key, (0, 0.0))
            if exp <= now:
                cnt = 0
            cnt += 1
            _local_counters[key] = (cnt, now + max(1, int(ttl_seconds)))
            return cnt
    try:
        p = r.pipeline()  # type: ignore[attr-defined]
        p.incr(key)
        p.expire(key, max(1, int(ttl_seconds)))
        res = await p.execute()
        return int(res[0]) if isinstance(res, (list, tuple)) and res else 0
    except Exception:
        return 0


async def record_pat_last_used(pat_id: str, ttl_seconds: int | None = None) -> None:
    r = await _get_redis()
    if r is None:
        return
    try:
        key = f"pat:last_used:{pat_id}"
        if ttl_seconds and ttl_seconds > 0:
            await r.set(key, str(int(asyncio.get_event_loop().time() * 1000)), ex=int(ttl_seconds))  # type: ignore[attr-defined]
        else:
            await r.set(key, str(int(asyncio.get_event_loop().time() * 1000)))  # type: ignore[attr-defined]
    except Exception:
        pass


__all__ = [
    "allow_refresh",
    "is_refresh_allowed",
    "revoke_refresh_family",
    "is_refresh_family_revoked",
    "revoke_access",
    "is_access_revoked",
    "_key_login_ip",
    "_key_login_user",
    "incr_login_counter",
    "record_pat_last_used",
]


