import wave
from importlib import reload

import pytest
from fastapi import HTTPException

from app import transcription


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "setup,exc,matcher",
    [
        ("missing", HTTPException, "file_not_found"),
        ("empty", ValueError, "empty_transcription"),
    ],
)
async def test_transcription_errors(tmp_path, monkeypatch, setup, exc, matcher):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    reload(transcription)
    if setup == "missing":
        path = tmp_path / "nope.wav"
    else:
        path = tmp_path / "empty.wav"
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            w.writeframes(b"")

        class Resp:
            text = ""

        async def fake_create(*args, **kwargs):
            return Resp()

        transcription._client = type(
            "C",
            (),
            {
                "audio": type(
                    "A",
                    (),
                    {"transcriptions": type("T", (), {"create": fake_create})()},
                )()
            },
        )()

    with pytest.raises(exc) as e:
        await transcription.transcribe_file(str(path))
    assert matcher in str(e.value)
    if isinstance(e.value, HTTPException):
        assert e.value.status_code == 400


@pytest.mark.asyncio
async def test_close_whisper_client_double(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    reload(transcription)
    transcription.get_whisper_client()
    await transcription.close_whisper_client()
    await transcription.close_whisper_client()
