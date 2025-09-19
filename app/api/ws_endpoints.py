import logging
from fastapi import APIRouter, Depends, Request, Response, WebSocket

from app.api._deps import dep_verify_ws
from app.deps.user import get_current_user_id

router = APIRouter(tags=["WebSocket"])
logger = logging.getLogger(__name__)


@router.websocket("/ws/transcribe")
async def websocket_transcribe(
    ws: WebSocket,
    user_id: str = Depends(get_current_user_id),
    _v: None = dep_verify_ws(),
):
    # Log WebSocket endpoint access
    client_ip = getattr(ws.client, 'host', 'unknown') if ws.client else 'unknown'
    user_agent = ws.headers.get("User-Agent", "unknown")

    logger.info("🎤 WS_TRANSCRIBE_ACCESS", extra={
        "endpoint": "/ws/transcribe",
        "user_id": user_id,
        "client_ip": client_ip,
        "user_agent": user_agent[:50] + "..." if len(user_agent) > 50 else user_agent,
        "timestamp": __import__('time').time(),
    })

    from app.api.sessions import websocket_transcribe as _wt

    try:
        return await _wt(ws, user_id)
    except Exception as e:
        logger.error("🚨 WS_TRANSCRIBE_ERROR", extra={
            "endpoint": "/ws/transcribe",
            "user_id": user_id,
            "error": str(e),
            "error_type": type(e).__name__,
            "client_ip": client_ip,
            "timestamp": __import__('time').time(),
        })
        raise


@router.websocket("/ws/storytime")
async def websocket_storytime(
    ws: WebSocket,
    user_id: str = Depends(get_current_user_id),
    _v: None = dep_verify_ws(),
):
    # Log WebSocket endpoint access
    client_ip = getattr(ws.client, 'host', 'unknown') if ws.client else 'unknown'
    user_agent = ws.headers.get("User-Agent", "unknown")

    logger.info("📖 WS_STORYTIME_ACCESS", extra={
        "endpoint": "/ws/storytime",
        "user_id": user_id,
        "client_ip": client_ip,
        "user_agent": user_agent[:50] + "..." if len(user_agent) > 50 else user_agent,
        "timestamp": __import__('time').time(),
    })

    from app.api.sessions import websocket_storytime as _ws

    try:
        return await _ws(ws, user_id)
    except Exception as e:
        logger.error("🚨 WS_STORYTIME_ERROR", extra={
            "endpoint": "/ws/storytime",
            "user_id": user_id,
            "error": str(e),
            "error_type": type(e).__name__,
            "client_ip": client_ip,
            "timestamp": __import__('time').time(),
        })
        raise


@router.websocket("/ws/health")
async def websocket_health(ws: WebSocket, _v: None = dep_verify_ws()):
    # Log WebSocket health check
    client_ip = getattr(ws.client, 'host', 'unknown') if ws.client else 'unknown'
    user_agent = ws.headers.get("User-Agent", "unknown")

    logger.info("🏥 WS_HEALTH_CHECK", extra={
        "endpoint": "/ws/health",
        "client_ip": client_ip,
        "user_agent": user_agent[:50] + "..." if len(user_agent) > 50 else user_agent,
        "timestamp": __import__('time').time(),
    })

    try:
        await ws.accept()
        await ws.send_text("healthy")
        await ws.close()

        logger.info("✅ WS_HEALTH_SUCCESS", extra={
            "endpoint": "/ws/health",
            "client_ip": client_ip,
            "timestamp": __import__('time').time(),
        })
    except Exception as e:
        logger.error("🚨 WS_HEALTH_ERROR", extra={
            "endpoint": "/ws/health",
            "error": str(e),
            "error_type": type(e).__name__,
            "client_ip": client_ip,
            "timestamp": __import__('time').time(),
        })
        raise


# Guard: HTTP -> WS error
@router.get("/ws/{path:path}")
@router.post("/ws/{path:path}")
@router.put("/ws/{path:path}")
@router.patch("/ws/{path:path}")
@router.delete("/ws/{path:path}")
async def websocket_http_handler(request: Request, path: str):
    # Log HTTP request to WebSocket endpoint
    client_ip = getattr(request.client, 'host', 'unknown') if request.client else 'unknown'
    user_agent = request.headers.get("User-Agent", "unknown")
    method = request.method

    logger.warning("🚫 HTTP_TO_WS_ERROR", extra={
        "endpoint": f"/ws/{path}",
        "method": method,
        "client_ip": client_ip,
        "user_agent": user_agent[:50] + "..." if len(user_agent) > 50 else user_agent,
        "error": "http_request_to_ws_endpoint",
        "timestamp": __import__('time').time(),
    })

    try:
        from app.auth_monitoring import record_ws_reconnect_attempt

        record_ws_reconnect_attempt(
            endpoint=f"/v1/ws/{path}",
            reason="http_request_to_ws_endpoint",
            user_id="unknown",
        )
    except Exception as e:
        logger.debug("Failed to record WS reconnect attempt", extra={
            "endpoint": f"/ws/{path}",
            "error": str(e),
            "timestamp": __import__('time').time(),
        })

    return Response(
        content="WebSocket endpoint requires WebSocket protocol",
        status_code=400,
        media_type="text/plain",
        headers={
            "X-WebSocket-Error": "protocol_required",
            "X-WebSocket-Reason": "HTTP requests not supported on WebSocket endpoints",
        },
    )
