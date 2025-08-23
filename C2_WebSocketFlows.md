## WebSocket Flows: endpoints, topics, publishers

### Endpoints (with 10 receipts)

| Method | Path | Subscriptions | Handler | Notes |
| --- | --- | --- | --- | --- |
| WS | /v1/ws/care | Client subscribes by sending `{action:"subscribe", topic:"resident:{id}"}` | app/api/care_ws.py::ws_care | Topic registry `_topics` with per-topic sets |
| WS | /v1/ws/music | No explicit subscribe; server pushes topic-tagged frames | app/api/music.py::ws_music | Broadcasts use `{topic, data}` frames |
| WS | /v1/transcribe | N/A (streaming RPC) | app/api/sessions.py::websocket_transcribe | Transcription stream orchestrator |
| WS | /v1/storytime | N/A (streaming RPC) | app/api/sessions.py::websocket_storytime | Transcription + JSONL logging |

Receipts

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

```363:371:app/api/music.py
@ws_router.websocket("/ws/music")
async def ws_music(ws: WebSocket, _user_id: str = Depends(get_current_user_id)):
    await verify_ws(ws)
    await ws.accept()
    _ws_clients.add(ws)
    try:
        while True:
            raw = await ws.receive()
```

```381:386:app/api/music.py
            # Simple ping/pong
            if data == "ping":
                await ws.send_text("pong")
    except Exception:
        pass
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

```70:76:app/api/care_ws.py
class WSTopicsInfo(BaseModel):
    subscribe_example: WSSubscribeExample = WSSubscribeExample()
    topics: list[str] = [
        "resident:{resident_id}",
    ]
    events_example: list[str] = [
        "device.heartbeat",
        "alert.created",
        "alert.acknowledged",
        "alert.resolved",
        "tv.config.updated",
    ]
```

```20:29:app/api/care_ws.py
async def _broadcast(topic: str, payload: dict) -> None:
    async with _lock:
        clients = set(_topics.get(topic) or set())
    if not clients:
        return
    dead = []
    for ws in list(clients):
        try:
            await ws.send_json({"topic": topic, "data": payload})
```

### Topic map (publishers and timing)

- resident:{resident_id}
  - alert.created: published by `app/api/care.py::create_alert` after creating a care alert; why: notify caregivers of a new alert.
  - alert.acknowledged: published by `app/api/care.py::ack_alert` after ack; why: update listeners that alert is acknowledged.
  - alert.resolved: could be added; `care.resolve_alert` does not currently broadcast (future enhancement). Why: lifecycle completion.
  - tv.config.updated: published by `app/api/tv.py::tv_put_config` after saving TV config; why: live TV config hot-reload.

- music.state
  - published by `app/api/music.py::music_command`, `set_vibe`, `restore_volume`, and `set_device` after state changes; why: sync UI state across clients.

- music.queue.updated
  - published by `app/api/music.py::get_queue` after queue retrieval; why: update UI with queue size changes.

- device.heartbeat
  - not broadcast today via WS; tracked in metrics in `care.heartbeat`. It is listed in `events_example` to document expected events. Why: potential future live presence updates.

### Where I got this
- WS endpoints, subscription, and broadcast helpers in `app/api/care_ws.py` and `app/api/music.py`.
- Event publishers in `app/api/care.py`, `app/api/tv.py`, and `app/api/music.py`.
- Session streaming endpoints in `app/api/sessions.py`.
