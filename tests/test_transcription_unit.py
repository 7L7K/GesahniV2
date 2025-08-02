import os
import sys
import asyncio
from importlib import reload
import pytest
from openai import OpenAIError

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_transcribe_file_success(tmp_path, monkeypatch):
    os.environ["OPENAI_API_KEY"] = "x"
    from app import transcription
    reload(transcription)
    audio = tmp_path / "a.wav"
    audio.write_text("data")

    class Resp:
        text = "hi"

    async def fake_create(*args, **kwargs):
        return Resp()

    fake_client = type(
        "C",
        (),
        {
            "audio": type(
                "A",
                (),
                {"transcriptions": type("T", (), {"create": fake_create})()}
            )()
        },
    )()
    monkeypatch.setattr(transcription, "_client", fake_client)

    out = asyncio.run(transcription.transcribe_file(str(audio)))
    assert out == "hi"


def test_transcribe_file_error(tmp_path, monkeypatch):
    os.environ["OPENAI_API_KEY"] = "x"
    from app import transcription
    reload(transcription)
    audio = tmp_path / "a.wav"
    audio.write_text("data")

    async def fake_create(*args, **kwargs):
        raise OpenAIError("boom")

    fake_client = type(
        "C",
        (),
        {
            "audio": type(
                "A",
                (),
                {"transcriptions": type("T", (), {"create": fake_create})()}
            )()
        },
    )()
    monkeypatch.setattr(transcription, "_client", fake_client)

    with pytest.raises(RuntimeError):
        asyncio.run(transcription.transcribe_file(str(audio)))
