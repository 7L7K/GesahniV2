from __future__ import annotations
from uuid import uuid4
from fastapi import Request, WebSocket
from ..telemetry import LogRecord, log_record_var

def get_current_user_id(request: Request | None = None, websocket: WebSocket | None = None) -> str:
    """
    Return the current user's identifier.
    - Pulled from log_record_var if set by HTTP middleware.
    - For WebSocket, fall back to hashing Authorization/IP via _anon_user_id.
    - Defaults to "local" outside of any context.
    Also attaches user_id to request.state or websocket.state.
    """
    # 1) Try to get existing LogRecord
    rec = log_record_var.get()
    if rec is None:
        # no HTTP context—create a minimal record so we have a place to stash
        rec = LogRecord(req_id=uuid4().hex)
        log_record_var.set(rec)

    user_id = rec.user_id or ""

    # 2) If WS and still empty, derive via anon helper
    if not user_id and websocket is not None:
        auth = websocket.headers.get("Authorization")
        from ..main import _anon_user_id  # local import to avoid circular
        user_id = _anon_user_id(auth)
        rec.user_id = user_id

    # 3) Final fallback
    if not user_id:
        user_id = "local"

    # 4) Attach to state for whichever object we got
    target = request or websocket
    if target is not None:
        target.state.user_id = user_id

    return user_id



__all__ = ["get_current_user_id"]
