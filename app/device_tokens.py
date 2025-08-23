from __future__ import annotations

import os
import time

_redis_client: object | None = None


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


def _key_pair_code(code: str) -> str:
    return f"pair:code:{code}"


def _key_device_token(token_id: str) -> str:
    return f"device:token:{token_id}"


def _key_device_for_owner(owner_id: str, device_id: str) -> str:
    return f"device:owner:{owner_id}:{device_id}"


async def store_pair_code(
    code: str, owner_id: str, device_label: str, ttl_seconds: int = 300
) -> None:
    r = await _get_redis()
    if r is None:
        return
    try:
        await r.hmset(_key_pair_code(code), {"owner_id": owner_id, "label": device_label})  # type: ignore[attr-defined]
        await r.expire(_key_pair_code(code), max(1, int(ttl_seconds)))  # type: ignore[attr-defined]
    except Exception:
        pass


async def consume_pair_code(code: str) -> tuple[str, str] | None:
    r = await _get_redis()
    if r is None:
        return None
    try:
        data = await r.hgetall(_key_pair_code(code))  # type: ignore[attr-defined]
        if not data:
            return None
        await r.delete(_key_pair_code(code))  # type: ignore[attr-defined]
        return (data.get("owner_id") or "", data.get("label") or "")
    except Exception:
        return None


async def upsert_device_token(
    token_id: str, owner_id: str, device_id: str, ttl_seconds: int
) -> None:
    r = await _get_redis()
    if r is None:
        return
    now_ms = int(time.time() * 1000)
    try:
        await r.hmset(
            _key_device_token(token_id),
            {  # type: ignore[attr-defined]
                "owner_id": owner_id,
                "device_id": device_id,
                "issued_at_ms": str(now_ms),
            },
        )
        await r.expire(_key_device_token(token_id), max(1, int(ttl_seconds)))  # type: ignore[attr-defined]
        await r.set(_key_device_for_owner(owner_id, device_id), token_id, ex=max(1, int(ttl_seconds)))  # type: ignore[attr-defined]
    except Exception:
        pass


async def get_device_token_info(token_id: str) -> dict | None:
    r = await _get_redis()
    if r is None:
        return None
    try:
        data = await r.hgetall(_key_device_token(token_id))  # type: ignore[attr-defined]
        return data or None
    except Exception:
        return None


async def revoke_device_token(token_id: str) -> None:
    r = await _get_redis()
    if r is None:
        return
    try:
        await r.delete(_key_device_token(token_id))  # type: ignore[attr-defined]
    except Exception:
        pass


__all__ = [
    "store_pair_code",
    "consume_pair_code",
    "upsert_device_token",
    "get_device_token_info",
    "revoke_device_token",
]
