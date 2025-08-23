from __future__ import annotations

from typing import Any

from fastapi import WebSocket, WebSocketException

from ..security import verify_ws


async def handle_reauth(ws: WebSocket, message: dict[str, Any]) -> bool:
    """Handle `{type: "reauth", token}` messages.

    Returns True if the connection context was updated; False if message not handled.
    Raises WebSocketException(4401) when token invalid.
    """
    if not isinstance(message, dict) or message.get("type") != "reauth":
        return False
    # Inject temporary header so verify_ws sees the token for this message
    token = message.get("token") or message.get("access_token")
    if not token:
        raise WebSocketException(code=4401)
    # Stash and override Authorization for a moment
    try:
        if token:
            # set a transient attribute for verify_ws to read
            ws.headers.__dict__["_list"].append((b"authorization", f"Bearer {token}".encode()))  # type: ignore[attr-defined]
    except Exception:
        pass
    try:
        await verify_ws(ws)
    except Exception:
        raise WebSocketException(code=4401)
    return True


__all__ = ["handle_reauth"]
