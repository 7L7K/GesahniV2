import os
import logging
from typing import Any

# audioop is deprecated in Python 3.13; keep optional with a small shim
try:  # pragma: no cover - import may be deprecated in future runtimes
    import audioop  # type: ignore
except Exception:  # pragma: no cover - fallback for environments without audioop
    audioop = None  # type: ignore

try:  # pragma: no cover - prefer modern SDK
    from openai import OpenAI as _SyncOpenAI  # type: ignore
except Exception:  # pragma: no cover - executed when dependency missing
    _SyncOpenAI = None  # type: ignore


# Defaults and config helpers
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "whisper-1")
_VAD_DEFAULT = 500


def _get_vad_threshold() -> int:
    """Return a safe integer VAD threshold from the environment.

    Falls back to a conservative default when parsing fails rather than
    crashing at import time.
    """

    raw = os.getenv("VAD_ENERGY_THRESHOLD", str(_VAD_DEFAULT))
    try:
        return int(raw)
    except Exception:
        logging.getLogger(__name__).warning(
            "Invalid VAD_ENERGY_THRESHOLD=%r; using default %d", raw, _VAD_DEFAULT
        )
        return _VAD_DEFAULT


logger = logging.getLogger(__name__)


# Cached sync OpenAI client for reuse
_client_sync: Any | None = None


def get_sync_whisper_client() -> Any:
    """Return a cached synchronous OpenAI client configured for resilience."""

    global _client_sync
    if _client_sync is not None:
        return _client_sync

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set")
    if _SyncOpenAI is None:
        raise RuntimeError("openai package not installed")

    # Configure optional timeout/retry if supported by the installed SDK version
    kwargs: dict[str, Any] = {"api_key": api_key}
    for k, v in ("timeout", 30), ("max_retries", 2):
        kwargs[k] = v
    try:
        _client_sync = _SyncOpenAI(**kwargs)  # type: ignore[arg-type]
    except TypeError:
        # Older SDKs may not support these keyword args
        _client_sync = _SyncOpenAI(api_key=api_key)  # type: ignore[call-arg]
    return _client_sync


def close_sync_whisper_client() -> None:
    """Close and clear the cached sync client if it provides a close()."""

    global _client_sync
    if _client_sync is not None:
        try:
            close = getattr(_client_sync, "close", None)
            if callable(close):
                close()
        except Exception:
            # Best-effort close; ignore errors
            pass
        finally:
            _client_sync = None


def transcribe_file(path: str, model: str | None = None) -> str:
    """Transcribe the given audio file using OpenAI's Whisper API (sync client).

    Raises ValueError("empty_transcription") when the API returns an empty text
    to match the async transcriber semantics.
    """

    # Resolve model with back-compat env fallback
    def _get_transcribe_model() -> str:
        env_model = os.getenv("OPENAI_TRANSCRIBE_MODEL")
        if env_model:
            return env_model
        legacy = os.getenv("WHISPER_MODEL")
        return legacy or "whisper-1"

    model = model or _get_transcribe_model()
    client = get_sync_whisper_client()
    try:
        # Optional file size guard to prevent runaway uploads
        max_bytes_raw = os.getenv("MAX_AUDIO_BYTES")
        if max_bytes_raw:
            try:
                max_bytes = int(max_bytes_raw)
            except Exception:
                logger.warning(
                    "Invalid MAX_AUDIO_BYTES=%r; ignoring size guard", max_bytes_raw
                )
            else:
                if max_bytes > 0:
                    try:
                        size = os.path.getsize(path)
                    except FileNotFoundError:
                        # Defer to the open() path which will raise consistently
                        pass
                    else:
                        if size > max_bytes:
                            raise ValueError("file_too_large")
        with open(path, "rb") as fh:
            resp = client.audio.transcriptions.create(model=model, file=fh)
        text = getattr(resp, "text", None)
        if not text:
            raise ValueError("empty_transcription")
        return str(text).strip()
    except FileNotFoundError:
        logger.debug("transcribe_file file not found: %s", path)
        raise
    except Exception as e:
        logger.exception("Transcription failed: %s", e)
        raise


def has_speech(chunk: bytes, threshold: int | None = None) -> bool:
    """Return True if the PCM chunk appears to contain speech.

    A tiny energy-based VAD used to short-circuit silent buffers when streaming
    audio. It falls back to ``True`` on any decoding issues to avoid dropping
    legitimate audio when the format is unexpected.
    """

    if not chunk:
        return False
    if threshold is None:
        threshold = _get_vad_threshold()
    try:
        if audioop is None:
            # Pure-Python RMS fallback to avoid passing all audio as speech.
            # Prefer int16 LE interpretation; fallback to 8-bit signed.
            try:
                if len(chunk) >= 2 and len(chunk) % 2 == 0:
                    total = 0
                    count = 0
                    for i in range(0, len(chunk), 2):
                        sample = int.from_bytes(chunk[i : i + 2], "little", signed=True)
                        total += sample * sample
                        count += 1
                    if count == 0:
                        return False
                    rms = int((total / count) ** 0.5)
                else:
                    total = 0
                    count = 0
                    for b in chunk:
                        s = int(b) - 128  # center to signed
                        total += s * s
                        count += 1
                    if count == 0:
                        return False
                    rms = int((total / count) ** 0.5)
            except Exception:
                # Conservative fallback on unexpected buffer formats
                return True
        else:
            # Try 16-bit samples; if that fails, fall back to 8-bit to avoid crashes
            try:
                rms = audioop.rms(chunk, 2)
            except Exception:
                rms = audioop.rms(chunk, 1)
    except Exception:
        return True
    return rms > threshold


__all__ = [
    "transcribe_file",
    "has_speech",
    "get_sync_whisper_client",
    "close_sync_whisper_client",
]
