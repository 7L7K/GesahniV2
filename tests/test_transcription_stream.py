from __future__ import annotations

import asyncio

import pytest


@pytest.fixture(autouse=True)
def _voice_env(monkeypatch):
    monkeypatch.setenv("VOICE_ENABLED", "1")
    yield


class DummyWS:
    def __init__(self):
        self.accepted = False
        self._q: asyncio.Queue[dict] = asyncio.Queue()
        self._closed = False
        # First message mimics metadata then audio chunk then end
        self._in = asyncio.Queue()

    async def accept(self):
        self.accepted = True

    async def receive(self):
        try:
            return await asyncio.wait_for(self._in.get(), timeout=0.2)
        except TimeoutError:
            raise RuntimeError("timeout")

    async def send_json(self, obj: dict):
        await self._q.put(obj)

    async def close(self):
        self._closed = True

    # helpers
    def feed(self, obj: dict):
        self._in.put_nowait(obj)

    async def drain(self):
        out = []
        while not self._q.empty():
            out.append(await self._q.get())
        return out


@pytest.mark.asyncio
async def test_ws_transcribe_emits_partial_final(monkeypatch):
    from app.transcription import TranscriptionStream

    # Stub PipecatSession to immediately yield two partials then finish, while emitting tts markers
    class FakeSession:
        async def start(self):
            return None

        async def stop(self):
            return None

        async def stream(self, it):
            yield "hello"
            yield "hello world"

    monkeypatch.setattr("app.transcription.PipecatSession", FakeSession)

    ws = DummyWS()
    # feed: audio bytes then end
    ws.feed({"bytes": b"abc"})
    ws.feed({"text": "end"})

    stream = TranscriptionStream(ws)  # type: ignore[arg-type]
    await stream.process()
    events = await ws.drain()
    kinds = [e.get("event") for e in events]
    assert "stt.state" in kinds and "stt.partial" in kinds and "stt.final" in kinds
