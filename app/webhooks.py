from __future__ import annotations

import hmac
import os
import time
from hashlib import sha256
from typing import Tuple


def _secret() -> bytes:
    val = os.getenv("WEBHOOK_SECRET", "")
    return val.encode("utf-8")


def sign_payload(body: bytes, nonce: str, timestamp: int | None = None) -> str:
    ts = int(timestamp or time.time())
    msg = f"{ts}.{nonce}.".encode("utf-8") + body
    mac = hmac.new(_secret(), msg, sha256).hexdigest()
    return f"v1={ts}:{nonce}:{mac}"


def verify_signature(body: bytes, signature: str, max_age: int = 300) -> bool:
    try:
        version, rest = signature.split("=", 1)
        if version != "v1":
            return False
        ts_str, nonce, mac = rest.split(":", 2)
        ts = int(ts_str)
    except Exception:
        return False
    if abs(time.time() - ts) > max_age:
        return False
    msg = f"{ts}.{nonce}.".encode("utf-8") + body
    expected = hmac.new(_secret(), msg, sha256).hexdigest()
    return hmac.compare_digest(expected, mac)


__all__ = ["sign_payload", "verify_signature"]


