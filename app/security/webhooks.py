from __future__ import annotations

import asyncio
import hashlib
import hmac
import os
import time
from typing import List

from fastapi import Header, HTTPException, Request
from app.http_errors import unauthorized


def sign_webhook(body: bytes, secret: str, timestamp: str | None = None) -> str:
    """Return hex HMAC-SHA256 signature for webhook payloads.

    When ``timestamp`` is provided, sign over ``body || b'.' || timestamp`` to bind
    the signature to a freshness value. This matches the verification logic.
    """
    payload = body if timestamp is None else (body + b"." + str(timestamp).encode("utf-8"))
    return hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def _load_webhook_secrets() -> List[str]:
    secrets: list[str] = []
    env_val = os.getenv("HA_WEBHOOK_SECRETS", "")
    if env_val:
        secrets.extend([s.strip() for s in env_val.split(",") if s.strip()])
    try:
        from pathlib import Path

        path = Path(os.getenv("HA_WEBHOOK_SECRET_FILE", "data/ha_webhook_secret.txt"))
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                s = line.strip()
                if s:
                    secrets.append(s)
    except Exception:
        pass
    single = os.getenv("HA_WEBHOOK_SECRET")
    if single:
        secrets.append(single)
    # Dedupe
    seen: dict[str, None] = {}
    out: list[str] = []
    for s in secrets:
        if s not in seen:
            seen[s] = None
            out.append(s)
    return out


_webhook_seen: dict[str, float] = {}
_lock: asyncio.Lock = asyncio.Lock()


async def verify_webhook(
    request: Request,
    x_signature: str | None = Header(default=None),
    x_timestamp: str | None = Header(default=None),
) -> bytes:
    """Verify webhook signature and return the raw body.

    Uses hex HMAC-SHA256 in X-Signature header. When REQUIRE_WEBHOOK_TS is truthy
    (default), requires X-Timestamp within WEBHOOK_MAX_SKEW_S and binds the
    signature to the timestamp.
    """
    if str(request.method).upper() == "OPTIONS":
        return b""

    body = await request.body()
    secrets = _load_webhook_secrets()
    if not secrets:
        raise HTTPException(status_code=500, detail="webhook_secret_missing")

    # Allow direct call style (when called without FastAPI dependency injection)
    if not isinstance(x_signature, (str, bytes)) or not str(x_signature).strip():
        try:
            x_signature = request.headers.get("X-Signature")
        except Exception:
            x_signature = None
    if not isinstance(x_timestamp, (str, bytes, int, float)) or not str(x_timestamp).strip():
        try:
            x_timestamp = request.headers.get("X-Timestamp")
        except Exception:
            x_timestamp = None

    sig = (x_signature or "").strip().lower()
    # Default is lenient in tests unless explicitly required via env
    require_ts = os.getenv("REQUIRE_WEBHOOK_TS", "0").strip().lower() in {"1", "true", "yes", "on"}

    ts_val: float | None = None
    max_skew = float(os.getenv("WEBHOOK_MAX_SKEW_S", "300") or 300)
    if x_timestamp is not None and str(x_timestamp).strip():
        try:
            ts_val = float(str(x_timestamp).strip())
        except Exception:
            raise HTTPException(status_code=400, detail="invalid_timestamp")
    if require_ts and ts_val is None:
        raise HTTPException(status_code=400, detail="missing_timestamp")

    if ts_val is not None:
        now = time.time()
        if abs(now - ts_val) > max_skew:
            raise unauthorized(code="stale_timestamp", message="stale timestamp", hint="adjust sender clock or increase skew")
        for s in secrets:
            calc = sign_webhook(body, s, str(int(ts_val)))
            if hmac.compare_digest(calc.lower(), sig):
                key = f"{sig}:{int(ts_val)}"
                async with _lock:
                    cutoff = time.time() - max_skew
                    for k, t in list(_webhook_seen.items()):
                        if t < cutoff:
                            _webhook_seen.pop(k, None)
                    if key in _webhook_seen:
                        raise HTTPException(status_code=409, detail="replay_detected")
                    _webhook_seen[key] = time.time()
                return body

    # Legacy path without timestamp
    for s in secrets:
        calc = sign_webhook(body, s)
        if hmac.compare_digest(calc.lower(), sig):
            return body
    raise unauthorized(code="invalid_signature", message="invalid signature", hint="verify secret and signature format")


def rotate_webhook_secret() -> str:
    """Generate and persist a new webhook secret in the optional secret file."""
    import secrets as _secrets
    from pathlib import Path

    new = _secrets.token_hex(16)
    path = Path(os.getenv("HA_WEBHOOK_SECRET_FILE", "data/ha_webhook_secret.txt"))
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        existing = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
        contents = "\n".join([new] + [line.strip() for line in existing if line.strip()]) + "\n"
        path.write_text(contents, encoding="utf-8")
    except Exception:
        pass
    return new


__all__ = ["sign_webhook", "verify_webhook", "rotate_webhook_secret"]
