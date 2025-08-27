"""
Stateless OAuth transaction store.

This module provides a simple key-value store for OAuth transactions,
storing PKCE code verifiers keyed by transaction ID.
"""

import logging
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# In-memory store for development; use Redis in production
_store: Dict[str, tuple[Dict[str, Any], float]] = {}


def put_tx(tx_id: str, data: Dict[str, Any], ttl_seconds: int = 600) -> None:
    """
    Store OAuth transaction data keyed by transaction ID.

    Args:
        tx_id: Transaction ID (UUID hex string)
        data: Transaction data (user_id, code_verifier, etc.)
        ttl_seconds: Time to live in seconds (default: 10 minutes)
    """
    expiry_time = time.time() + ttl_seconds
    _store[tx_id] = (data, expiry_time)

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


def pop_tx(tx_id: str) -> Optional[Dict[str, Any]]:
    """
    Atomically fetch and delete OAuth transaction data.

    Args:
        tx_id: Transaction ID

    Returns:
        Transaction data if found and not expired, None otherwise
    """
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


def get_tx(tx_id: str) -> Optional[Dict[str, Any]]:
    """
    Fetch OAuth transaction data without deleting it.

    Args:
        tx_id: Transaction ID

    Returns:
        Transaction data if found and not expired, None otherwise
    """
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


def dump_store() -> Dict[str, Any]:
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
