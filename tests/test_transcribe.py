import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import transcribe


def test_transcribe_file(monkeypatch, tmp_path):
    audio_path = tmp_path / "audio.wav"
    audio_path.write_bytes(b"dummy")

    def fake_transcribe(model, file, api_key=None):
        assert model == "whisper-test"
        assert api_key == "sk-test"
        file.read()
        return {"text": "hello"}

    monkeypatch.setattr(transcribe, "WHISPER_MODEL", "whisper-test")
    monkeypatch.setattr(transcribe, "OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(transcribe.openai.Audio, "transcribe", fake_transcribe)
    result = transcribe.transcribe_file(str(audio_path))
    assert result == "hello"
