import os
import importlib


def _fake_client_with_capture():
    class Resp:
        text = "ok"

    class T:
        def __init__(self):
            self.last_model = None

        def create(self, *args, **kwargs):  # sync path
            self.last_model = kwargs.get("model")
            return Resp()

    class A:
        def __init__(self):
            self.transcriptions = T()

    class C:
        def __init__(self):
            self.audio = A()

    return C()


def test_model_resolution_precedence(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    from app import transcribe

    importlib.reload(transcribe)
    fake = _fake_client_with_capture()
    monkeypatch.setattr(transcribe, "_client_sync", fake)

    os.environ.pop("WHISPER_MODEL", None)
    monkeypatch.setenv("OPENAI_TRANSCRIBE_MODEL", "gpt-4o-mini-transcribe")
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"data")
    out = transcribe.transcribe_file(str(audio))
    assert out == "ok"
    assert fake.audio.transcriptions.last_model == "gpt-4o-mini-transcribe"


def test_max_audio_bytes_guard(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    from app import transcribe

    importlib.reload(transcribe)
    # 1 byte limit
    monkeypatch.setenv("MAX_AUDIO_BYTES", "1")
    # Seed client
    fake = _fake_client_with_capture()
    monkeypatch.setattr(transcribe, "_client_sync", fake)
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"too big")
    try:
        transcribe.transcribe_file(str(audio))
        assert False, "expected ValueError(file_too_large)"
    except ValueError as e:
        assert str(e) == "file_too_large"


def test_has_speech_python_fallback(monkeypatch):
    from app import transcribe

    # Force audioop absence and use fallback
    monkeypatch.setattr(transcribe, "audioop", None)
    # Silence (zeros) -> not speech
    assert transcribe.has_speech(b"\x00\x00" * 64, threshold=10) is False
    # Loud int16 samples -> speech
    loud = (b"\xff\x7f" * 64)  # 32767
    assert transcribe.has_speech(loud, threshold=100) is True


