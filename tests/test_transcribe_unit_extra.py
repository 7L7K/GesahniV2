import importlib
import os


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
    loud = b"\xff\x7f" * 64  # 32767
    assert transcribe.has_speech(loud, threshold=100) is True


def test_missing_api_key_raises(monkeypatch):
    import importlib

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    from app import transcribe

    importlib.reload(transcribe)
    # get_sync_whisper_client should raise when key missing
    try:
        transcribe.get_sync_whisper_client()
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        assert "OPENAI_API_KEY" in str(e)


def test_missing_openai_package_raises(monkeypatch):
    import importlib

    monkeypatch.setenv("OPENAI_API_KEY", "x")
    from app import transcribe

    importlib.reload(transcribe)
    # Simulate missing SDK
    monkeypatch.setattr(transcribe, "_SyncOpenAI", None)
    try:
        transcribe.get_sync_whisper_client()
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        assert "openai" in str(e).lower()


def test_client_cached_and_close(monkeypatch):
    import importlib

    monkeypatch.setenv("OPENAI_API_KEY", "x")
    from app import transcribe

    importlib.reload(transcribe)

    class Fake:
        def __init__(self, *a, **k):
            self.closed = False

        def close(self):
            self.closed = True

    monkeypatch.setattr(transcribe, "_SyncOpenAI", Fake)
    c1 = transcribe.get_sync_whisper_client()
    c2 = transcribe.get_sync_whisper_client()
    assert c1 is c2
    transcribe.close_sync_whisper_client()
    assert getattr(c1, "closed", False) is True
    # next call returns a new instance
    c3 = transcribe.get_sync_whisper_client()
    assert c3 is not c1


def test_legacy_whisper_model_env(monkeypatch, tmp_path):
    import importlib

    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.delenv("OPENAI_TRANSCRIBE_MODEL", raising=False)
    monkeypatch.setenv("WHISPER_MODEL", "whisper-9")
    from app import transcribe

    importlib.reload(transcribe)

    class Resp:
        text = "ok"

    class T:
        def __init__(self):
            self.last_model = None

        def create(self, *a, **k):
            self.last_model = k.get("model")
            return Resp()

    class A:
        def __init__(self):
            self.transcriptions = T()

    class C:
        def __init__(self):
            self.audio = A()

    fake = C()
    monkeypatch.setattr(transcribe, "_client_sync", fake)
    p = tmp_path / "a.wav"
    p.write_bytes(b"x")
    out = transcribe.transcribe_file(str(p))
    assert out == "ok"
    assert fake.audio.transcriptions.last_model == "whisper-9"
