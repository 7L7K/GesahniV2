from __future__ import annotations

import os
import time

try:  # pragma: no cover - optional heavy dep in CI
    from openai import AsyncOpenAI
except Exception:  # pragma: no cover

    class AsyncOpenAI:  # type: ignore
        def __init__(self, *a, **k):
            raise RuntimeError("openai package not installed")


from ...metrics import (
    TTS_COST_USD,
    TTS_LATENCY_SECONDS,
    TTS_REQUEST_COUNT,
    normalize_model_label,
)

OPENAI_TTS_PRICING_PER_1K_CHARS = {
    "tts-1": 0.015,
    "tts-1-hd": 0.030,
}

# gpt-4o-mini-tts is priced per-minute; we estimate from output seconds
OPENAI_TTS_MINI_PER_MINUTE = 0.015


def _pick_model(tier: str) -> tuple[str, str]:
    # Map tier to model and a label
    tier_l = (tier or "").strip().lower()
    if tier_l in {"tts1", "tts-1", "standard"}:
        return os.getenv("OPENAI_TTS_MODEL", "tts-1"), "tts1"
    if tier_l in {"tts1_hd", "tts-1-hd", "hd"}:
        return os.getenv("OPENAI_TTS_HD_MODEL", "tts-1-hd"), "tts1_hd"
    # default to mini tts
    return os.getenv("OPENAI_TTS_MINI_MODEL", "gpt-4o-mini-tts"), "mini_tts"


async def synthesize_openai_tts(
    *,
    text: str,
    tier: str,
    voice: str | None = None,
    format: str = "wav",
) -> tuple[bytes, float, str]:
    """Return (audio_bytes, cost_usd_estimate, tier_label).

    Uses OpenAI TTS endpoints; picks model by tier.
    """
    model, tier_label = _pick_model(tier)
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set")
    client = AsyncOpenAI(api_key=api_key)

    # Use normalized model and reduced dimensions to prevent cardinality explosion
    normalized_model = normalize_model_label(model)
    TTS_REQUEST_COUNT.labels(
        "openai", tier_label, os.getenv("VOICE_MODE", "auto"), "auto", normalized_model
    ).inc()
    start = time.perf_counter()
    # Note: official API surface is audio.speech.create with model=tts-1/hd and voice
    # For gpt-4o-mini-tts the surface differs in preview SDKs; here we normalize
    out_format = (
        "wav" if format.lower() not in {"mp3", "opus", "aac"} else format.lower()
    )
    chosen_voice = voice or os.getenv("OPENAI_TTS_VOICE", "alloy")

    # Fallback path for environments where SDK may not include audio.speech
    try:
        resp = await client.audio.speech.create(  # type: ignore[attr-defined]
            model=model,
            voice=chosen_voice,
            input=text,
            format=out_format,
        )
        audio_bytes = (
            resp.read() if hasattr(resp, "read") else getattr(resp, "content", b"")
        )
        if not isinstance(audio_bytes, (bytes, bytearray)):
            # Some SDKs return base64 string; normalize
            try:
                import base64

                audio_bytes = base64.b64decode(audio_bytes)
            except Exception:
                audio_bytes = b""
    except Exception as e:  # pragma: no cover - guarded path
        # Attempt a generic completions-then-ssml path is out-of-scope; bubble up
        raise RuntimeError(f"openai_tts_failed: {e}") from e

    latency = time.perf_counter() - start
    TTS_LATENCY_SECONDS.labels("openai", tier_label).observe(latency)

    # Rough cost estimate
    if model.startswith("gpt-4o-mini-tts"):
        # Estimate seconds from bytes assuming 16kHz mono 16-bit PCM ~ 32kB/s if wav pcm16
        # This is an approximation; if compressed, this underestimates length.
        seconds = max(0.0, len(audio_bytes) / 32000.0)
        cost = (seconds / 60.0) * OPENAI_TTS_MINI_PER_MINUTE
    else:
        chars = len(text)
        per_1k = OPENAI_TTS_PRICING_PER_1K_CHARS.get(
            model, OPENAI_TTS_PRICING_PER_1K_CHARS.get("tts-1", 0.015)
        )
        cost = (chars / 1000.0) * per_1k
    TTS_COST_USD.labels("openai", tier_label).observe(cost)
    return bytes(audio_bytes), float(cost), tier_label
