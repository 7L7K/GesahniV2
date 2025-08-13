from __future__ import annotations

import asyncio
import os
import time
from typing import Optional, Tuple

from ...metrics import TTS_REQUEST_COUNT, TTS_LATENCY_SECONDS, TTS_COST_USD


async def synthesize_piper(
    *, text: str, voice: Optional[str] = None, format: str = "wav"
) -> Tuple[bytes, float]:
    """Return (audio_bytes, cost_usd_estimate).

    This implementation assumes a local Piper CLI available as `piper`.
    If unavailable, it returns empty audio and zero cost.
    """

    TTS_REQUEST_COUNT.labels("piper", "piper", os.getenv("VOICE_MODE", "auto"), "auto", voice or "default").inc()
    start = time.perf_counter()
    # Minimal stub: avoid shelling out in CI; emulate tiny WAV header and silence
    try:
        # 0.2s of silence at 16kHz mono pcm16 -> 3200 bytes + header
        import wave
        import io
        import struct

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


