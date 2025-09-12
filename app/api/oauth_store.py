"""
Stateless OAuth transaction store.

This module provides a simple key-value store for OAuth transactions,
storing PKCE code verifiers keyed by transaction ID.

Backed by Redis when REDIS_URL is configured and reachable; otherwise
falls back to an in-process dictionary suitable only for single-instance
development. Using Redis ensures transactions survive across instances
behind a load balancer.
"""

import json
import logging
import os
import pickle
import time
from typing import Any

logger = logging.getLogger(__name__)

# In-memory store for development; use Redis in production
_store: dict[str, tuple[dict[str, Any], float]] = {}

# File-based store for cross-process sharing during testing
_store_file = os.path.join(os.path.dirname(__file__), '..', '..', 'oauth_store.pkl')

def _load_store():
    """Load store from file if it exists."""
    global _store
    try:
        if os.path.exists(_store_file):
            with open(_store_file, 'rb') as f:
                _store = pickle.load(f)
                logger.info(f"OAuth store: Loaded {len(_store)} items from file")
    except Exception as e:
        logger.warning(f"OAuth store: Failed to load from file: {e}")

def _save_store():
    """Save store to file."""
    try:
        with open(_store_file, 'wb') as f:
            pickle.dump(_store, f)
        logger.debug("OAuth store: Saved to file")
    except Exception as e:
        logger.warning(f"OAuth store: Failed to save to file: {e}")

# Load store on import
_load_store()

_redis = None

def _get_redis_sync():
    global _redis
    if _redis is not None:
        return _redis
    url = os.getenv("REDIS_URL")
    if not url:
        return None
    try:
        import redis  # type: ignore
    except Exception:
        return None
    try:
        _redis = redis.from_url(url, encoding="utf-8", decode_responses=True)
        # health check
        _redis.ping()
        logger.info("OAuth store: Redis connection established")
        return _redis
    except Exception as e:
        logger.warning(f"OAuth store: failed to connect Redis, using memory: {e}")
        _redis = None
        return None


def put_tx(tx_id: str, data: dict[str, Any], ttl_seconds: int = 600) -> None:
    """
    Store OAuth transaction data keyed by transaction ID.

    Args:
        tx_id: Transaction ID (UUID hex string)
        data: Transaction data (user_id, code_verifier, etc.)
        ttl_seconds: Time to live in seconds (default: 10 minutes)
    """
    expiry_time = time.time() + ttl_seconds

    # Prefer Redis when available to ensure cross-instance consistency
    r = _get_redis_sync()
    if r is not None:
        try:
            key = f"oauth:tx:{tx_id}"
            payload = json.dumps({"data": data})
            # Atomic set with expiry
            r.setex(key, int(ttl_seconds), payload)
        except Exception as e:
            logger.warning(
                f"OAuth store: Redis put_tx failed (falling back to memory): {e}"
            )
            _store[tx_id] = (data, expiry_time)
    else:
        _store[tx_id] = (data, expiry_time)
        _save_store()  # Save to file for cross-process sharing

    logger.info("🔐 OAuth TX STORED", extra={
        "meta": {
            "tx_id": tx_id,
            "data_keys": list(data.keys()),
            "user_id": data.get("user_id", "unknown"),
            "has_code_verifier": "code_verifier" in data,
            "ttl_seconds": ttl_seconds,
            "expires_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(expiry_time)),
            "store_size": len(_store)
        }
    })


def pop_tx(tx_id: str) -> dict[str, Any] | None:
    """
    Atomically fetch and delete OAuth transaction data.

    Args:
        tx_id: Transaction ID

    Returns:
        Transaction data if found and not expired, None otherwise
    """
    # Try Redis first (atomic GETDEL when available)
    r = _get_redis_sync()
    if r is not None:
        try:
            key = f"oauth:tx:{tx_id}"
            raw = None
            try:
                # Redis 6.2+ supports GETDEL
                raw = r.getdel(key)  # type: ignore[attr-defined]
            except Exception:
                # Fallback: pipeline WATCH/GET/DEL
                with r.pipeline() as p:
                    p.watch(key)
                    raw = r.get(key)
                    p.multi()
                    p.delete(key)
                    p.execute()
            if not raw:
                logger.warning(
                    "🔐 OAuth TX NOT FOUND",
                    extra={"meta": {"tx_id": tx_id, "store": "redis"}},
                )
                return None
            try:
                obj = json.loads(raw)
                data = obj.get("data") if isinstance(obj, dict) else None
            except Exception:
                data = None
            if not isinstance(data, dict):
                logger.warning(
                    "🔐 OAuth TX INVALID PAYLOAD",
                    extra={"meta": {"tx_id": tx_id, "store": "redis"}},
                )
                return None
            logger.info(
                "🔐 OAuth TX POPPED",
                extra={
                    "meta": {
                        "tx_id": tx_id,
                        "user_id": data.get("user_id", "unknown"),
                        "data_keys": list(data.keys()),
                        "store": "redis",
                    }
                },
            )
            return data
        except Exception as e:
            logger.warning(
                f"OAuth store: Redis pop_tx failed (falling back to memory): {e}"
            )

    # Load from file first (in case another process updated it)
    _load_store()

    row = _store.pop(tx_id, None)
    if not row:
        logger.warning("🔐 OAuth TX NOT FOUND", extra={
            "meta": {
                "tx_id": tx_id,
                "store_size": len(_store),
                "available_tx_ids": list(_store.keys())[:5]  # Show first 5 for debugging
            }
        })
        return None

    # Save updated store to file
    _save_store()

    data, exp = row
    current_time = time.time()
    is_expired = current_time > exp

    if is_expired:
        logger.warning("🔐 OAuth TX EXPIRED", extra={
            "meta": {
                "tx_id": tx_id,
                "user_id": data.get("user_id", "unknown"),
                "expired_seconds_ago": int(current_time - exp),
                "expiry_time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(exp))
            }
        })
        return None

    logger.info("🔐 OAuth TX POPPED", extra={
        "meta": {
            "tx_id": tx_id,
            "user_id": data.get("user_id", "unknown"),
            "data_keys": list(data.keys()),
            "has_code_verifier": "code_verifier" in data,
            "seconds_until_expiry": int(exp - current_time),
            "store_size": len(_store)
        }
    })

    return data


def debug_store() -> dict[str, Any]:
    """Debug function to show current store contents."""
    _load_store()
    return {
        "store_size": len(_store),
        "tx_ids": list(_store.keys())[:10],  # Show first 10 tx_ids
        "store_file_exists": os.path.exists(_store_file),
        "store_file_size": os.path.getsize(_store_file) if os.path.exists(_store_file) else 0
    }

def get_tx(tx_id: str) -> dict[str, Any] | None:
    """
    Fetch OAuth transaction data without deleting it.

    Args:
        tx_id: Transaction ID

    Returns:
        Transaction data if found and not expired, None otherwise
    """
    # Try Redis first
    r = _get_redis_sync()
    if r is not None:
        try:
            key = f"oauth:tx:{tx_id}"
            raw = r.get(key)
            if not raw:
                logger.debug(
                    "🔐 OAuth TX GET - NOT FOUND", extra={"meta": {"tx_id": tx_id, "store": "redis"}}
                )
                return None
            try:
                obj = json.loads(raw)
                data = obj.get("data") if isinstance(obj, dict) else None
            except Exception:
                data = None
            if not isinstance(data, dict):
                return None
            return data
        except Exception as e:
            logger.warning(
                f"OAuth store: Redis get_tx failed (falling back to memory): {e}"
            )

    row = _store.get(tx_id)
    if not row:
        logger.debug("🔐 OAuth TX GET - NOT FOUND", extra={
            "meta": {
                "tx_id": tx_id,
                "store_size": len(_store)
            }
        })
        return None

    data, exp = row
    current_time = time.time()
    is_expired = current_time > exp

    if is_expired:
        logger.warning("🔐 OAuth TX GET - EXPIRED", extra={
            "meta": {
                "tx_id": tx_id,
                "user_id": data.get("user_id", "unknown"),
                "expired_seconds_ago": int(current_time - exp)
            }
        })
        # Expired - clean it up
        _store.pop(tx_id, None)
        return None

    logger.debug("🔐 OAuth TX GET - SUCCESS", extra={
        "meta": {
            "tx_id": tx_id,
            "user_id": data.get("user_id", "unknown"),
            "seconds_until_expiry": int(exp - current_time)
        }
    })

    return data


def cleanup_expired() -> None:
    """Clean up expired transactions."""
    now = time.time()
    expired = [tx_id for tx_id, (_, exp) in _store.items() if now > exp]

    if expired:
        logger.info("🧹 OAuth TX CLEANUP", extra={
            "meta": {
                "expired_count": len(expired),
                "expired_tx_ids": expired[:10],  # Show first 10
                "store_size_before": len(_store)
            }
        })

        for tx_id in expired:
            data, exp = _store[tx_id]
            logger.debug("🗑️  OAuth TX CLEANED", extra={
                "meta": {
                    "tx_id": tx_id,
                    "user_id": data.get("user_id", "unknown"),
                    "expired_seconds_ago": int(now - exp)
                }
            })
            _store.pop(tx_id, None)

        logger.info("✅ OAuth TX CLEANUP COMPLETE", extra={
            "meta": {
                "cleaned_count": len(expired),
                "store_size_after": len(_store)
            }
        })
    else:
        logger.debug("🧹 OAuth TX CLEANUP - No expired transactions")


def dump_store() -> dict[str, Any]:
    """Debug function to dump current store state."""
    now = time.time()
    result = {
        "store_size": len(_store),
        "transactions": {}
    }

    for tx_id, (data, exp) in _store.items():
        result["transactions"][tx_id] = {
            "user_id": data.get("user_id", "unknown"),
            "data_keys": list(data.keys()),
            "expires_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(exp)),
            "seconds_until_expiry": max(0, int(exp - now)),
            "is_expired": now > exp
        }

    logger.info("📊 OAuth TX STORE DUMP", extra={
        "meta": result
    })

    return result
