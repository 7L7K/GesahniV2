import os
import logging
try:  # pragma: no cover - import may be deprecated in future runtimes
    import audioop  # type: ignore
except Exception:  # pragma: no cover - fallback for environments without audioop
    audioop = None  # type: ignore

try:  # pragma: no cover - prefer modern SDK
    from openai import OpenAI as _SyncOpenAI  # type: ignore
except Exception:  # pragma: no cover - executed when dependency missing
    _SyncOpenAI = None  # type: ignore

WHISPER_MODEL = os.getenv("WHISPER_MODEL", "whisper-1")
VAD_ENERGY_THRESHOLD = int(os.getenv("VAD_ENERGY_THRESHOLD", "500"))

logger = logging.getLogger(__name__)


def transcribe_file(path: str, model: str | None = None) -> str:
    """Transcribe the given audio file using OpenAI's Whisper API (sync client)."""
    model = model or WHISPER_MODEL
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set")
    if _SyncOpenAI is None:
        raise RuntimeError("openai package not installed")
    try:
        client = _SyncOpenAI(api_key=api_key)
        with open(path, "rb") as fh:
            resp = client.audio.transcriptions.create(model=model, file=fh)
        text = getattr(resp, "text", "")
        return str(text or "").strip()
    except FileNotFoundError as e:
        logger.debug("transcribe_file file not found: %s", path)
        raise
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
        if audioop is None:
            return True
        rms = audioop.rms(chunk, 2)  # assume 16-bit samples
    except Exception:
        return True
    return rms > threshold


__all__ = ["transcribe_file", "has_speech"]
