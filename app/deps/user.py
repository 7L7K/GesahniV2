from __future__ import annotations

from fastapi import Request, WebSocket

from ..telemetry import log_record_var


def get_current_user_id(request: Request | WebSocket | None = None) -> str:
    """Return the current user's identifier.

    The ID is pulled from ``log_record_var`` which is populated by the request
    tracing middleware.  When called outside of a request context, ``"local"``
    is returned.  If a ``Request`` or ``WebSocket`` is provided the resolved
    ``user_id`` is also attached to ``request.state`` for easy downstream
    access.
    """

    rec = log_record_var.get()
    user_id = rec.user_id if rec and rec.user_id else "local"
    if request is not None:
        request.state.user_id = user_id
    return user_id

__all__ = ["get_current_user_id"]
