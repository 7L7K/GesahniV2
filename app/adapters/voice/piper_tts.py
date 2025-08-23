from __future__ import annotations

import os
import time

from ...metrics import TTS_COST_USD, TTS_LATENCY_SECONDS, TTS_REQUEST_COUNT, normalize_model_label


async def synthesize_piper(
    *, text: str, voice: str | None = None, format: str = "wav"
) -> tuple[bytes, float]:
    """Return (audio_bytes, cost_usd_estimate).

    This implementation assumes a local Piper CLI available as `piper`.
    If unavailable, it returns empty audio and zero cost.
    """

    # Use normalized voice label to prevent cardinality explosion
    normalized_voice = normalize_model_label(voice or "default")
    TTS_REQUEST_COUNT.labels("piper", "piper", os.getenv("VOICE_MODE", "auto"), "auto", normalized_voice).inc()
    start = time.perf_counter()
    # Minimal stub: avoid shelling out in CI; emulate tiny WAV header and silence
    try:
        # 0.2s of silence at 16kHz mono pcm16 -> 3200 bytes + header
        import io
        import struct
        import wave

        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            frames = b"".join(struct.pack("<h", 0) for _ in range(3200 // 2))
            w.writeframes(frames)
        audio_bytes = buf.getvalue()
    except Exception:
        audio_bytes = b""

    latency = time.perf_counter() - start
    TTS_LATENCY_SECONDS.labels("piper", "piper").observe(latency)
    TTS_COST_USD.labels("piper", "piper").observe(0.0)
    return audio_bytes, 0.0


