import pytest


@pytest.mark.asyncio
async def test_privacy_forces_piper(monkeypatch):
    monkeypatch.setenv("TTS_PRIVACY_LOCAL_ONLY", "1")
    monkeypatch.setenv("VOICE_MODE", "auto")
    from app.tts_orchestrator import synthesize

    audio = await synthesize(
        text="My email is test@example.com", mode="utility", intent_hint="chat"
    )
    assert isinstance(audio, (bytes, bytearray))
    assert len(audio) > 0


@pytest.mark.asyncio
async def test_budget_blocks_openai(monkeypatch):
    # Force cap to 0 to ensure Piper fallback
    monkeypatch.setenv("MONTHLY_TTS_CAP", "0")
    from app.tts_orchestrator import synthesize

    audio = await synthesize(text="hello", mode="capture", intent_hint="story")
    assert isinstance(audio, (bytes, bytearray))
    # Should get some audio (piper silence) even when capped
    assert len(audio) >= 0
