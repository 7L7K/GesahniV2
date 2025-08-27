from __future__ import annotations

import base64
import hmac
import hashlib
import os
import secrets
import time
from typing import Any

logger_name = "app.oauth_state"

# In-memory store for oauth transactions: state -> record
_oauth_tx_store: dict[str, dict[str, Any]] = {}


def _now() -> float:
    return time.time()


def _base64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _base64url_decode(s: str) -> bytes:
    # Add padding
    pad = -len(s) % 4
    if pad:
        s += "=" * pad
    return base64.urlsafe_b64decode(s.encode("utf-8"))


def _sign(payload: str) -> str:
    secret = os.getenv("JWT_STATE_SECRET", "")
    if not secret:
        return ""
    mac = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256)
    return mac.hexdigest()


def make_state(user_id: str, session_id: str) -> str:
    """Create a signed, self-contained state token.

    Format: base64url(user_id|session_id|nonce|ts|sig)
    If JWT_STATE_SECRET is not set, produce an unsigned state (store-only mode).
    """
    nonce = secrets.token_hex(8)
    ts = str(int(_now()))
    core = f"{user_id}|{session_id}|{nonce}|{ts}"
    sig = _sign(core)
    if sig:
        raw = f"{core}|{sig}".encode("utf-8")
    else:
        raw = core.encode("utf-8")
    return _base64url_encode(raw)


def parse_and_verify_state(state: str, max_age_seconds: int = 600) -> dict[str, Any]:
    """Parse state and verify HMAC and timestamp.

    Returns dict with keys: user_id, session_id, nonce, ts
    Raises ValueError on invalid or expired state.
    """
    try:
        raw = _base64url_decode(state)
        parts = raw.decode("utf-8").split("|")
    except Exception as e:
        raise ValueError("state_invalid") from e

    if len(parts) not in (4, 5):
        raise ValueError("state_invalid")

    user_id, session_id, nonce, ts = parts[0], parts[1], parts[2], parts[3]
    sig = parts[4] if len(parts) == 5 else ""

    # If a secret is configured, require and validate signature
    secret = os.getenv("JWT_STATE_SECRET", "")
    if secret:
        if not sig:
            raise ValueError("state_invalid")
        core = f"{user_id}|{session_id}|{nonce}|{ts}"
        expected = _sign(core)
        if not hmac.compare_digest(expected, sig):
            raise ValueError("state_invalid")

    # Validate timestamp
    try:
        ts_i = int(ts)
    except Exception:
        raise ValueError("state_invalid")

    if _now() - ts_i > max_age_seconds:
        raise ValueError("state_expired")

    return {"user_id": user_id, "session_id": session_id, "nonce": nonce, "ts": ts_i}


def save_oauth_tx(state: str, record: dict[str, Any], ttl_seconds: int = 600) -> None:
    record_copy = dict(record)
    record_copy["created_at"] = _now()
    record_copy["ttl"] = ttl_seconds
    _oauth_tx_store[state] = record_copy


def get_oauth_tx(state: str) -> dict[str, Any] | None:
    rec = _oauth_tx_store.get(state)
    if not rec:
        return None
    if _now() - rec.get("created_at", 0) > rec.get("ttl", 600):
        # expired
        _oauth_tx_store.pop(state, None)
        return None
    return rec


def mark_oauth_tx_completed(state: str) -> None:
    rec = _oauth_tx_store.get(state)
    if not rec:
        return
    rec["status"] = "COMPLETED"
    rec["completed_at"] = _now()


def mark_oauth_tx_consummated(state: str) -> None:
    """Mark the oauth transaction as consummated (finalized)."""
    rec = _oauth_tx_store.get(state)
    if not rec:
        return
    rec["status"] = "CONSUMMATED"
    rec["consummated_at"] = _now()


def cleanup_expired_oauth_tx() -> None:
    now = _now()
    to_del = [s for s, r in _oauth_tx_store.items() if now - r.get("created_at", 0) > r.get("ttl", 600)]
    for s in to_del:
        _oauth_tx_store.pop(s, None)


