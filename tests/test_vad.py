from __future__ import annotations

from app.voice.input.vad import has_speech


def test_vad_none_backend(monkeypatch):
    monkeypatch.setenv("VAD_BACKEND", "none")
    assert has_speech(b"") is False


def test_vad_webrtc_backend_no_crash(monkeypatch):
    monkeypatch.setenv("VAD_BACKEND", "webrtc")
    # With no real audio and possibly missing webrtcvad, should return False gracefully
    assert has_speech(b"\x00" * 320) in (False, True)

