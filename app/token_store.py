from __future__ import annotations

import os
import asyncio
from typing import Optional


_redis_client: Optional[object] = None


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


async def revoke_refresh_family(sid: str, ttl_seconds: int) -> None:
    r = await _get_redis()
    if r is None:
        return
    try:
        await r.set(_key_revoked_refresh_family(sid), "1", ex=max(1, int(ttl_seconds)))  # type: ignore[attr-defined]
    except Exception:
        pass


async def is_refresh_family_revoked(sid: str) -> bool:
    r = await _get_redis()
    if r is None:
        return False
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
        return 0
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


