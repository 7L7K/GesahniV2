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
        except TimeoutError:
            raise RuntimeError("timeout")

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


def _fake_session(partial_texts: list[str], tokens: list[str] | None = None):
    class Fake:
        def __init__(self, event_cb=None):
            self.event_cb = event_cb
        async def start(self):
            return None
        async def stop(self):
            return None
        async def stream(self, it):
            if tokens and self.event_cb:
                for t in tokens:
                    await self.event_cb("llm.token", {"token": t})
            for p in partial_texts:
                yield p
    return Fake


@pytest.mark.asyncio
async def test_initial_state_event(monkeypatch):
    from app.transcription import TranscriptionStream
    monkeypatch.setenv("VOICE_ENABLED", "1")
    monkeypatch.setattr("app.transcription.PipecatSession", _fake_session(["hello"]))
    ws = DummyWS()
    ws.feed({"bytes": b"x"})
    ws.feed({"text": "end"})
    stream = TranscriptionStream(ws)  # type: ignore[arg-type]
    await stream.process()
    events = await ws.drain()
    assert events and events[0].get("event") == "stt.state"


@pytest.mark.asyncio
async def test_final_punctuation_preserved(monkeypatch):
    from app.transcription import TranscriptionStream
    monkeypatch.setenv("VOICE_ENABLED", "1")
    monkeypatch.setattr("app.transcription.PipecatSession", _fake_session(["ok!"]))
    ws = DummyWS()
    ws.feed({"bytes": b"x"})
    ws.feed({"text": "end"})
    stream = TranscriptionStream(ws)  # type: ignore[arg-type]
    await stream.process()
    events = await ws.drain()
    finals = [e.get("text") for e in events if e.get("event") == "stt.final"]
    assert finals and finals[0].endswith("!")


@pytest.mark.asyncio
async def test_error_emits_network_shaky(monkeypatch):
    from app.transcription import TranscriptionStream
    monkeypatch.setenv("VOICE_ENABLED", "1")

    class Boom:
        async def start(self):
            return None
        async def stop(self):
            return None
        async def stream(self, it):
            raise RuntimeError("boom")

    monkeypatch.setattr("app.transcription.PipecatSession", Boom)
    ws = DummyWS()
    ws.feed({"bytes": b"x"})
    ws.feed({"text": "end"})
    stream = TranscriptionStream(ws)  # type: ignore[arg-type]
    await stream.process()
    events = await ws.drain()
    assert any(e.get("error") == "listening_network_shaky" for e in events)


@pytest.mark.asyncio
async def test_events_order_state_then_partial_then_final(monkeypatch):
    from app.transcription import TranscriptionStream
    monkeypatch.setenv("VOICE_ENABLED", "1")
    monkeypatch.setattr("app.transcription.PipecatSession", _fake_session(["a", "ab"]))
    ws = DummyWS()
    ws.feed({"bytes": b"x"})
    ws.feed({"text": "end"})
    stream = TranscriptionStream(ws)  # type: ignore[arg-type]
    await stream.process()
    events = await ws.drain()
    kinds = [e.get("event") for e in events]
    assert kinds[0] == "stt.state"
    assert "stt.partial" in kinds and "stt.final" in kinds


@pytest.mark.asyncio
async def test_voice_enabled_default_true(monkeypatch):
    from app.transcription import TranscriptionStream
    monkeypatch.delenv("VOICE_ENABLED", raising=False)
    monkeypatch.setattr("app.transcription.PipecatSession", _fake_session(["ok"]))
    ws = DummyWS()
    ws.feed({"bytes": b"x"})
    ws.feed({"text": "end"})
    await TranscriptionStream(ws).process()  # type: ignore[arg-type]
    events = await ws.drain()
    assert any(e.get("event") == "stt.final" for e in events)


@pytest.mark.asyncio
async def test_wake_mode_any_accepts_either(monkeypatch):
    from app.transcription import TranscriptionStream
    monkeypatch.setenv("WAKE_MODE", "any")
    monkeypatch.setattr("app.transcription.PipecatSession", _fake_session(["ok"]))
    ws = DummyWS()
    ws.feed({"bytes": b"x"})
    ws.feed({"text": json.dumps({"wake": True})})
    ws.feed({"bytes": b"y"})
    ws.feed({"text": "end"})
    await TranscriptionStream(ws).process()  # type: ignore[arg-type]
    events = await ws.drain()
    assert any(e.get("event") == "stt.final" for e in events)


@pytest.mark.asyncio
async def test_wake_mode_both_requires_both(monkeypatch):
    from app.transcription import TranscriptionStream
    monkeypatch.setenv("WAKE_MODE", "both")
    monkeypatch.setattr("app.transcription.PipecatSession", _fake_session(["ok"]))
    ws = DummyWS()
    ws.feed({"bytes": b"x"})  # gated
    ws.feed({"text": json.dumps({"wake": True})})  # still gated
    ws.feed({"text": json.dumps({"ptt": True, "wake": True})})  # both -> allow
    ws.feed({"bytes": b"y"})
    ws.feed({"text": "end"})
    await TranscriptionStream(ws).process()  # type: ignore[arg-type]
    events = await ws.drain()
    assert any(e.get("event") == "stt.final" for e in events)


@pytest.mark.asyncio
async def test_unknown_control_ignored(monkeypatch):
    from app.transcription import TranscriptionStream
    monkeypatch.setattr("app.transcription.PipecatSession", _fake_session(["ok"]))
    ws = DummyWS()
    ws.feed({"text": json.dumps({"foo": 1})})
    ws.feed({"bytes": b"z"})
    ws.feed({"text": "end"})
    await TranscriptionStream(ws).process()  # type: ignore[arg-type]
    events = await ws.drain()
    assert any(e.get("event") == "stt.final" for e in events)


@pytest.mark.asyncio
async def test_has_speech_monkeypatch(monkeypatch):
    from app.transcription import TranscriptionStream
    monkeypatch.setattr("app.transcription.has_speech", lambda b: False)
    monkeypatch.setattr("app.transcription.PipecatSession", _fake_session([]))
    ws = DummyWS()
    ws.feed({"bytes": b"x"})
    ws.feed({"text": "end"})
    await TranscriptionStream(ws).process()  # type: ignore[arg-type]
    events = await ws.drain()
    # Only state, no partials
    kinds = [e.get("event") for e in events]
    assert kinds and kinds[0] == "stt.state" and "stt.partial" not in kinds


