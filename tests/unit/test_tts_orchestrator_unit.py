from importlib import reload


def test_tts_cache_hit(monkeypatch):
    import app.tts_orchestrator as tts

    monkeypatch.setenv("TTS_CACHE_TTL_S", "60")
    # Force Piper to avoid OpenAI deps
    monkeypatch.setenv("VOICE_MODE", "always_piper")
    reload(tts)

    # First call populates cache
    audio1 = (
        tts.__dict__["asyncio"]
        .get_event_loop()
        .run_until_complete(tts.synthesize(text="hello", mode="utility"))
    )
    assert isinstance(audio1, (bytes, bytearray))
    # Second call should return cached bytes quickly
    audio2 = (
        tts.__dict__["asyncio"]
        .get_event_loop()
        .run_until_complete(tts.synthesize(text="hello", mode="utility"))
    )
    assert audio2 == audio1


def test_tts_daily_cap_autodegrade(monkeypatch):
    import app.tts_orchestrator as tts

    monkeypatch.setenv("VOICE_MODE", "auto")
    monkeypatch.setenv("DAILY_TTS_CAP_USD", "0.0")
    reload(tts)
    # With cap 0, any call should select Piper path (no exception)
    audio = (
        tts.__dict__["asyncio"]
        .get_event_loop()
        .run_until_complete(tts.synthesize(text="status ok", mode="utility"))
    )
    assert isinstance(audio, (bytes, bytearray))
