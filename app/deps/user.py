from __future__ import annotations
import os
from hashlib import sha256
from uuid import uuid4
from fastapi import Request, WebSocket, HTTPException
import jwt

from ..telemetry import LogRecord, log_record_var

JWT_SECRET = os.getenv("JWT_SECRET")


def _hash(value: str, length: int = 32) -> str:
    return sha256(value.encode("utf-8")).hexdigest()[:length]


def get_current_user_id(
    request: Request = None,
    websocket: WebSocket = None,
) -> str:
    """Return the current user's identifier.

    Preference order:
    1. Existing log record set by middleware.
    2. JWT "user_id" claim when API token/secret is configured.
    3. Hash of Authorization header.
    4. Hash of client IP.
    5. Fallback to "local".
    The resolved ID is attached to request/websocket state.
    """
    target = request or websocket

    # 1) Grab or initialize our log record
    rec = log_record_var.get()
    if rec is None:
        rec = LogRecord(req_id=uuid4().hex)
        log_record_var.set(rec)

    user_id = rec.user_id or ""

    # 2) Try JWT-based user_id
    auth_header = None
    if target:
        auth_header = target.headers.get("Authorization")
    token = None
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1]

    if token and JWT_SECRET:
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
            user_id = payload.get("user_id") or user_id
        except jwt.PyJWTError:
            # Unauthorized if token is malformed or invalid
            raise HTTPException(status_code=401, detail="Invalid authentication token")

    # 3) Fallback: hash the raw Authorization header
    if not user_id and auth_header:
        user_id = _hash(auth_header)

    # 4) Fallback: hash client IP / X-Forwarded-For
    if not user_id and target:
        ip = target.headers.get("X-Forwarded-For") or (
            target.client.host if target.client else None
        )
        if ip:
            user_id = _hash(ip, length=12)

    # 5) Last resort
    if not user_id:
        user_id = "local"

    # Attach to record + state
    rec.user_id = user_id
    if target:
        target.state.user_id = user_id

    return user_id


__all__ = ["get_current_user_id"]
