from fastapi import APIRouter, Depends, Request, Response, WebSocket

from app.api._deps import dep_verify_ws
from app.deps.user import get_current_user_id

router = APIRouter(tags=["Care"])


@router.websocket("/ws/transcribe")
async def websocket_transcribe(
    ws: WebSocket,
    user_id: str = Depends(get_current_user_id),
    _v: None = dep_verify_ws(),
):
    from app.api.sessions import websocket_transcribe as _wt

    return await _wt(ws, user_id)


@router.websocket("/ws/storytime")
async def websocket_storytime(
    ws: WebSocket,
    user_id: str = Depends(get_current_user_id),
    _v: None = dep_verify_ws(),
):
    from app.api.sessions import websocket_storytime as _ws

    return await _ws(ws, user_id)


@router.websocket("/ws/health")
async def websocket_health(ws: WebSocket, _v: None = dep_verify_ws()):
    await ws.accept()
    await ws.send_text("healthy")
    await ws.close()


# Guard: HTTP -> WS error
@router.get("/ws/{path:path}")
@router.post("/ws/{path:path}")
@router.put("/ws/{path:path}")
@router.patch("/ws/{path:path}")
@router.delete("/ws/{path:path}")
async def websocket_http_handler(request: Request, path: str):
    try:
        from app.auth_monitoring import record_ws_reconnect_attempt

        record_ws_reconnect_attempt(
            endpoint=f"/v1/ws/{path}",
            reason="http_request_to_ws_endpoint",
            user_id="unknown",
        )
    except Exception:
        pass
    return Response(
        content="WebSocket endpoint requires WebSocket protocol",
        status_code=400,
        media_type="text/plain",
        headers={
            "X-WebSocket-Error": "protocol_required",
            "X-WebSocket-Reason": "HTTP requests not supported on WebSocket endpoints",
        },
    )
