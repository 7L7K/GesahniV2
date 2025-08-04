from __future__ import annotations

from uuid import uuid4

from fastapi import Request, WebSocket

from ..telemetry import LogRecord, log_record_var


def get_current_user_id(request: Request) -> str:
    """Return the current user's identifier.

    The ID is pulled from ``log_record_var`` which is populated by the request
    tracing middleware. When called outside of a request context, ``"local"`` is
    returned. If a ``Request`` or ``WebSocket`` is provided the resolved
    ``user_id`` is also attached to ``request.state`` for easy downstream
    access.
    """

    rec = log_record_var.get()
    if rec is None:
        rec = LogRecord(req_id=uuid4().hex)
        log_record_var.set(rec)

    user_id = rec.user_id

    if not user_id and isinstance(request, WebSocket):
        from ..main import _anon_user_id

        user_id = _anon_user_id(request.headers.get("Authorization"))
        rec.user_id = user_id

    if not user_id:
        user_id = "local"

    request.state.user_id = user_id

    return user_id


__all__ = ["get_current_user_id"]
