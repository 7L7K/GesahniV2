"""Helpers for transcribing audio with OpenAI Whisper.

The real project uses the official ``openai`` package.  To allow the test suite
to run in environments where this heavy optional dependency isn't installed we
guard the import and fall back to a minimal stub.  Tests monkey‑patch the
transcriber so the stub is never exercised directly.
"""

import logging
import os

from fastapi import HTTPException

try:  # pragma: no cover - executed when openai is available
    from openai import AsyncClient as OpenAI
    from openai import OpenAIError
except Exception:  # pragma: no cover - exercised when dependency missing

    class OpenAIError(Exception):
        pass

    class OpenAI:  # type: ignore[misc]
        def __init__(self, *_, **__):
            raise RuntimeError("openai package not installed")


TRANSCRIBE_MODEL = os.getenv("OPENAI_TRANSCRIBE_MODEL", "whisper-1")

logger = logging.getLogger(__name__)
_client: OpenAI | None = None


def get_whisper_client() -> OpenAI:
    """Return a singleton OpenAI client with runtime API key lookup."""

    global _client
    if _client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY not set")
        _client = OpenAI(api_key=api_key)
    return _client


async def close_whisper_client() -> None:
    """Close the cached Whisper client if present."""

    global _client
    if _client is not None:
        await _client.close()
        _client = None


async def transcribe_file(path: str, model: str | None = None) -> str:
    """
    Send the audio file at `path` to OpenAI Whisper via the v1 SDK
    and return the transcript text.
    """
    model = model or TRANSCRIBE_MODEL

    logger.debug("transcribe_file start: %s", path)
    client = get_whisper_client()
    try:
        with open(path, "rb") as f:
            resp = await client.audio.transcriptions.create(
                model=model,
                file=f,
            )
    except FileNotFoundError as e:
        logger.debug("transcribe_file file not found: %s", path)
        raise HTTPException(status_code=400, detail="file_not_found") from e
    except OpenAIError as e:
        logger.debug("transcribe_file openai error: %s", e)
        raise RuntimeError(f"Whisper API error: {e}") from e
    except Exception as e:
        logger.debug("transcribe_file error: %s", e)
        raise RuntimeError(f"Failed to read or send {path!r}: {e}") from e

    text = getattr(resp, "text", None)
    if not text:
        raise ValueError("empty_transcription")

    logger.debug("transcribe_file success: %s", path)
    return text
