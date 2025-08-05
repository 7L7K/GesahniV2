from __future__ import annotations
import os
from uuid import uuid4
from fastapi import Request, WebSocket, HTTPException
import jwt

from ..telemetry import LogRecord, log_record_var

JWT_SECRET = os.getenv("JWT_SECRET")


def get_current_user_id(
    request: Request = None,
    websocket: WebSocket = None,
) -> str:
    """Return the current user's identifier.

    Preference order:
    1. Existing log record set by middleware.
    2. JWT "user_id" claim when API token/secret is configured.
    3. Fallback to anonymous.
    The resolved ID is attached to request/websocket state when authenticated.
    """
    target = request or websocket

    # 1) Grab or initialize our log record
    rec = log_record_var.get()
    if rec is None:
        rec = LogRecord(req_id=uuid4().hex)
        log_record_var.set(rec)

    user_id = ""

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

    if not user_id:
        user_id = "anon"

    # Attach to record + state for authenticated users only
    rec.user_id = user_id
    if target and user_id != "anon":
        target.state.user_id = user_id

    return user_id


__all__ = ["get_current_user_id"]
