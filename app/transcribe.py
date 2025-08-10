import os
import logging
import audioop

try:  # pragma: no cover - exercised when openai is installed
    import openai
except Exception:  # pragma: no cover - executed when dependency missing
    openai = None  # type: ignore

WHISPER_MODEL = os.getenv("WHISPER_MODEL", "whisper-1")
VAD_ENERGY_THRESHOLD = int(os.getenv("VAD_ENERGY_THRESHOLD", "500"))

logger = logging.getLogger(__name__)


def transcribe_file(path: str, model: str | None = None) -> str:
    """Transcribe the given audio file using OpenAI's Whisper API."""
    model = model or WHISPER_MODEL
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set")
    if openai is None:
        raise RuntimeError("openai package not installed")
    try:
        with open(path, "rb") as fh:
            resp = openai.Audio.transcribe(model=model, file=fh, api_key=api_key)
        if isinstance(resp, dict):
            text = resp.get("text", "")
        else:
            text = getattr(resp, "text", str(resp))
        return text.strip()
    except Exception as e:
        logger.exception("Transcription failed: %s", e)
        raise


def has_speech(chunk: bytes, threshold: int = VAD_ENERGY_THRESHOLD) -> bool:
    """Return True if the PCM chunk appears to contain speech.

    A tiny energy-based VAD used to short-circuit silent buffers when streaming
    audio.  It falls back to ``True`` on any decoding issues to avoid dropping
    legitimate audio when the format is unexpected.
    """

    if not chunk:
        return False
    try:
        rms = audioop.rms(chunk, 2)  # assume 16-bit samples
    except Exception:
        return True
    return rms > threshold


__all__ = ["transcribe_file", "has_speech"]
