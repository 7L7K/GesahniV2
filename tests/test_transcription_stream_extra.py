import asyncio

import pytest


class DummyWS:
    def __init__(self, messages):
        self._in = asyncio.Queue()
        for m in messages:
            self._in.put_nowait(m)
        self.sent = []
        self.accepted = False

    async def accept(self):
        self.accepted = True

    async def receive(self):
        try:
            return await asyncio.wait_for(self._in.get(), timeout=0.2)
        except TimeoutError as err:
            raise RuntimeError("timeout") from err

    async def send_json(self, obj: dict):
        self.sent.append(obj)

    async def close(self):
        return None


@pytest.mark.asyncio
async def test_final_uses_last_partial(monkeypatch):
    from app.transcription import TranscriptionStream

    class FakeSession:
        async def start(self):
            return None

        async def stop(self):
            return None

        async def stream(self, it):
            yield "hello"
            yield "hello world"

    monkeypatch.setenv("VOICE_ENABLED", "1")
    monkeypatch.setattr("app.transcription.PipecatSession", FakeSession)
    ws = DummyWS(messages=[{"bytes": b"abc"}, {"text": "end"}])
    stream = TranscriptionStream(ws)  # type: ignore[arg-type]
    await stream.process()
    finals = [m for m in ws.sent if m.get("event") == "stt.final"]
    assert finals and finals[-1]["text"].startswith("hello world")


@pytest.mark.asyncio
async def test_final_when_no_partials(monkeypatch):
    from app.transcription import TranscriptionStream

    class FakeSession:
        async def start(self):
            return None

        async def stop(self):
            return None

        async def stream(self, it):
            if False:
                yield "never"

    monkeypatch.setenv("VOICE_ENABLED", "1")
    monkeypatch.setattr("app.transcription.PipecatSession", FakeSession)
    ws = DummyWS(messages=[{"bytes": b"abc"}, {"text": "end"}])
    stream = TranscriptionStream(ws)  # type: ignore[arg-type]
    await stream.process()
    finals = [m for m in ws.sent if m.get("event") == "stt.final"]
    assert finals and finals[-1]["text"] in {"", "."}
