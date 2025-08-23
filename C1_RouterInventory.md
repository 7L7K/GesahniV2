## WebSocket Router Inventory

This document enumerates WebSocket endpoints and the HTTP endpoints that publish to WebSocket topics.

### WebSocket endpoints

| Method | Path | Auth/Deps | Handler | Purpose |
| --- | --- | --- | --- | --- |
| WS | /v1/ws/care | verify_ws | app/api/care_ws.py::ws_care | Topic-based pub/sub (subscribe to `resident:{id}`) |
| WS | /v1/ws/music | verify_ws | app/api/music.py::ws_music | Broadcast music state/queue updates |
| WS | /v1/transcribe | get_current_user_id | app/api/sessions.py::websocket_transcribe | Bidirectional streaming transcription |
| WS | /v1/storytime | get_current_user_id | app/api/sessions.py::websocket_storytime | Streaming transcription + JSONL logging |

### HTTP endpoints that publish to WS

| Method | Path | Handler | Publishes | Side-effects |
| --- | --- | --- | --- | --- |
| POST | /v1/care/alerts | app/api/care.py::create_alert | resident:{resident_id} event=alert.created | Insert alert, insert event, enqueue SMS |
| POST | /v1/care/alerts/{alert_id}/ack | app/api/care.py::ack_alert | resident:{resident_id} event=alert.acknowledged | Update alert, insert event, metrics |
| PUT | /v1/tv/config | app/api/tv.py::tv_put_config | resident:{resident_id} event=tv.config.updated | Persist TV config, WS broadcast |
| POST | /v1/music | app/api/music.py::music_command | topic=music.state | Update music state, external provider calls |
| POST | /v1/vibe | app/api/music.py::set_vibe | topic=music.state | Update vibe, cap volume, external provider calls |
| POST | /v1/music/restore | app/api/music.py::restore_volume | topic=music.state | Restore ducked volume |
| GET | /v1/queue | app/api/music.py::get_queue | topic=music.queue.updated | Broadcast queue counts after fetch |
| POST | /v1/music/device | app/api/music.py::set_device | topic=music.state | Device transfer + broadcast |

### Receipts (10)

```79:86:app/api/care_ws.py
@router.get("/ws/care", response_model=WSTopicsInfo, responses={200: {"model": WSTopicsInfo}})
async def ws_care_docs(_user_id: str = Depends(get_current_user_id)):
    """WebSocket entry point documentation.

    Connect to ``/v1/ws/care`` and send a JSON message to subscribe to a topic.
    Example payload: ``{"action": "subscribe", "topic": "resident:r1"}``.
    """
```

```89:101:app/api/care_ws.py
@router.websocket("/ws/care")
async def ws_care(ws: WebSocket, _user_id: str = Depends(get_current_user_id)):
    await verify_ws(ws)
    await ws.accept()
    try:
        while True:
            msg = await ws.receive_json()
            # {action: 'subscribe', topic: 'resident:r1'}
            if isinstance(msg, dict) and msg.get("action") == "subscribe":
                topic = str(msg.get("topic") or "").strip()
                if topic:
                    async with _lock:
                        _topics.setdefault(topic, set()).add(ws)
```

```113:116:app/api/care_ws.py
async def broadcast_resident(resident_id: str, event: str, data: dict) -> None:
    topic = f"resident:{resident_id}"
    await _broadcast(topic, {"event": event, **data})
```

```206:213:app/api/care.py
    await insert_event(aid, "created", {})
    # Notify caregivers (MVP: one SMS)
    await _notify_sms(body.resident_id, f"Alert: {body.kind} ({body.severity})")
    try:
        from .care_ws import broadcast_resident  # local import to avoid cycle at import time
        await broadcast_resident(body.resident_id, "alert.created", {"id": aid, "kind": body.kind, "severity": body.severity})
    except Exception:
        pass
```

```230:233:app/api/care.py
    try:
        from .care_ws import broadcast_resident
        await broadcast_resident(rec["resident_id"], "alert.acknowledged", {"id": alert_id, "by": (body.by if body else None)})
    except Exception:
        pass
```

```621:629:app/api/tv.py
    try:
        from app.api.care_ws import broadcast_resident
        await broadcast_resident(resident_id or "me", "tv.config.updated", {"config": {
            "ambient_rotation": new_ambient,
            "rail": rail,
            "quiet_hours": new_qh.model_dump() if new_qh else None,
            "default_vibe": new_vibe,
        }})
    except Exception:
        pass
```

```343:353:app/api/music.py
_ws_clients: set[WebSocket] = set()

async def _broadcast(topic: str, payload: dict) -> None:
    if not _ws_clients:
        return
    dead: list[WebSocket] = []
    for ws in list(_ws_clients):
        try:
            await ws.send_json({"topic": topic, "data": payload})
```

```763:769:app/api/music.py
    if not PROVIDER_SPOTIFY:
        asyncio.create_task(_broadcast("music.queue.updated", {"count": 0}))
        return {"current": None, "up_next": [], "skip_count": state.skip_count}
    _qres = _provider_queue(user_id)
    current, queue = (await _qres) if inspect.isawaitable(_qres) else _qres
    # Broadcast queue update for listeners
    asyncio.create_task(_broadcast("music.queue.updated", {"count": len(queue)}))
```

```900:907:app/api/music.py
    if PROVIDER_SPOTIFY:
        try:
            client = SpotifyClient(user_id)
            await client.transfer(body.device_id, play=True)
        except Exception:
            # Non-fatal in tests or when auth not configured
            pass
    await _broadcast("music.state", await get_state(user_id))
```

```163:170:app/api/sessions.py
@router.websocket("/transcribe")
async def websocket_transcribe(
    ws: WebSocket,
    user_id: str = Depends(get_current_user_id),
):
    stream = TranscriptionStream(ws)
    await stream.process()
```

```172:182:app/api/sessions.py
@router.websocket("/storytime")
async def websocket_storytime(
    ws: WebSocket, user_id: str = Depends(get_current_user_id)
):
    """Storytime streaming: audio → Whisper transcription with JSONL logging.

    Uses the same streaming mechanics as ``/transcribe`` but appends each
    incremental transcript chunk to `stories/` for later summarization.
    """
```

### Where I got this
- WebSocket endpoints and subscription/broadcast code in `app/api/care_ws.py` and `app/api/music.py`.
- Event-producing HTTP endpoints in `app/api/care.py`, `app/api/tv.py`, and `app/api/music.py`.
- Transcription WS endpoints in `app/api/sessions.py`.
