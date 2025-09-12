from __future__ import annotations

import asyncio
import json

import pytest


class DummyWS:
    def __init__(self):
        self.accepted = False
        self._q: asyncio.Queue[dict] = asyncio.Queue()
        self._in = asyncio.Queue()

    async def accept(self):
        self.accepted = True

    async def receive(self):
        try:
            return await asyncio.wait_for(self._in.get(), timeout=0.2)
        except TimeoutError as err:
            raise RuntimeError("timeout") from err

    async def send_json(self, obj: dict):
        await self._q.put(obj)

    async def close(self):
        await self._q.put({"event": "closed"})

    # helpers
    def feed(self, obj: dict):
        self._in.put_nowait(obj)

    async def drain(self):
        out = []
        while not self._q.empty():
            out.append(await self._q.get())
        return out


@pytest.mark.asyncio
async def test_voice_disabled(monkeypatch):
    from app.transcription import TranscriptionStream

    monkeypatch.setenv("VOICE_ENABLED", "0")
    ws = DummyWS()
    ws.feed({"bytes": b"abc"})
    stream = TranscriptionStream(ws)  # type: ignore[arg-type]
    await stream.process()
    events = await ws.drain()
    assert any(e.get("error") == "voice_disabled" for e in events)


@pytest.mark.asyncio
async def test_ptt_gating(monkeypatch):
    from app.transcription import TranscriptionStream

    class FakeSession:
        async def start(self):
            return None

        async def stop(self):
            return None

        async def stream(self, it):
            yield "heard"

    monkeypatch.setenv("VOICE_ENABLED", "1")
    monkeypatch.setenv("WAKE_MODE", "ptt")
    monkeypatch.setattr("app.transcription.PipecatSession", FakeSession)

    ws = DummyWS()
    ws.feed({"bytes": b"abc"})  # gated until ptt
    ws.feed({"text": json.dumps({"ptt": True})})
    ws.feed({"bytes": b"def"})  # allowed
    ws.feed({"text": "end"})
    stream = TranscriptionStream(ws)  # type: ignore[arg-type]
    await stream.process()
    events = await ws.drain()
    kinds = [e.get("event") for e in events]
    assert "stt.state" in kinds and "stt.partial" in kinds


@pytest.mark.asyncio
async def test_wake_gating(monkeypatch):
    from app.transcription import TranscriptionStream

    class FakeSession:
        async def start(self):
            return None

        async def stop(self):
            return None

        async def stream(self, it):
            yield "ok"

    monkeypatch.setenv("VOICE_ENABLED", "1")
    monkeypatch.setenv("WAKE_MODE", "wake")
    monkeypatch.setattr("app.transcription.PipecatSession", FakeSession)

    ws = DummyWS()
    ws.feed({"bytes": b"aaa"})  # gated
    ws.feed({"text": json.dumps({"wake": True})})
    ws.feed({"bytes": b"bbb"})  # allowed now
    ws.feed({"text": "end"})
    stream = TranscriptionStream(ws)  # type: ignore[arg-type]
    await stream.process()
    events = await ws.drain()
    assert any(e.get("event") == "stt.partial" for e in events)


@pytest.mark.asyncio
async def test_llm_token_and_final_punctuation(monkeypatch):
    from app.transcription import TranscriptionStream

    class FakeSession:
        def __init__(self, event_cb=None):
            self.event_cb = event_cb

        async def start(self):
            if self.event_cb:
                await self.event_cb("tts.start", {})
            return None

        async def stop(self):
            if self.event_cb:
                await self.event_cb("tts.stop", {})
            return None

        async def stream(self, it):
            if self.event_cb:
                await self.event_cb("llm.token", {"token": "Hello"})
            yield "Hello world"

    monkeypatch.setenv("VOICE_ENABLED", "1")
    monkeypatch.setattr("app.transcription.PipecatSession", FakeSession)

    ws = DummyWS()
    ws.feed({"bytes": b"abc"})
    ws.feed({"text": "end"})
    stream = TranscriptionStream(ws)  # type: ignore[arg-type]
    await stream.process()
    events = await ws.drain()
    kinds = [e.get("event") for e in events]
    assert "llm.token" in kinds and "tts.start" in kinds and "tts.stop" in kinds
    finals = [e.get("text") for e in events if e.get("event") == "stt.final"]
    assert finals and finals[0].endswith((".", "!", "?"))
