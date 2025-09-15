import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from fastapi import Depends, FastAPI, WebSocket
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import app.security as security


# From codex/refactor-http-helper-and-apply-misc-fixes
def test_rate_limit_prunes_empty(monkeypatch):
    monkeypatch.setattr(security, "_requests", {"ip": [time.time() - 120]})
    asyncio.run(security._apply_rate_limit("ip", record=False))
    assert "ip" not in security._requests


# Added in response to bucket reset fix
def test_bucket_counters_reset(monkeypatch):
    bucket = {}
    key = "ip"
    limit = 1
    period = 0.05
    assert security._bucket_rate_limit(key, bucket, limit, period)
    assert not security._bucket_rate_limit(key, bucket, limit, period)
    time.sleep(period)
    assert security._bucket_rate_limit(key, bucket, limit, period)


# From main
def _build_app(monkeypatch):
    monkeypatch.setattr(security, "RATE_LIMIT", 1)
    monkeypatch.setattr(security, "_http_requests", {})
    monkeypatch.setattr(security, "_ws_requests", {})

    app = FastAPI()

    @app.get("/ping")
    async def ping(_: None = Depends(security.rate_limit)):
        return {"ok": True}

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket):
        await security.rate_limit_ws(ws)
        await ws.accept()
        await ws.receive_text()
        await ws.close()

    return app


def test_http_limit_does_not_block_ws(monkeypatch):
    app = _build_app(monkeypatch)
    client = TestClient(app)
    headers = {"X-Forwarded-For": "1.2.3.4"}

    assert client.get("/ping", headers=headers).status_code == 200
    assert client.get("/ping", headers=headers).status_code == 429

    with client.websocket_connect("/ws", headers=headers) as ws:
        ws.send_text("hi")

    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/ws", headers=headers) as ws:
            ws.send_text("hi")
    assert exc.value.code == 1013


def test_ws_limit_does_not_block_http(monkeypatch):
    app = _build_app(monkeypatch)
    client = TestClient(app)
    headers = {"X-Forwarded-For": "5.6.7.8"}

    with client.websocket_connect("/ws", headers=headers) as ws:
        ws.send_text("hi")

    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/ws", headers=headers) as ws:
            ws.send_text("hi")
    assert exc.value.code == 1013

    assert client.get("/ping", headers=headers).status_code == 200


def test_x_forwarded_for_splits(monkeypatch):
    app = _build_app(monkeypatch)
    client = TestClient(app)
    h1 = {"X-Forwarded-For": "1.1.1.1, 2.2.2.2"}
    h2 = {"X-Forwarded-For": "1.1.1.1, 3.3.3.3"}

    assert client.get("/ping", headers=h1).status_code == 200
    assert client.get("/ping", headers=h2).status_code == 429
