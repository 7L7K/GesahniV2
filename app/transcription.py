"""Helpers for transcribing audio with OpenAI Whisper.

The real project uses the official ``openai`` package.  To allow the test suite
to run in environments where this heavy optional dependency isn't installed we
guard the import and fall back to a minimal stub.  Tests monkey‑patch the
transcriber so the stub is never exercised directly.
"""

import json
import logging
import os
import uuid
from typing import AsyncIterator

from fastapi import HTTPException, WebSocket

from .adapters.voice.pipecat_adapter import PipecatSession
from .transcribe import has_speech

try:  # pragma: no cover - executed when openai is available
    from openai import AsyncOpenAI as OpenAI  # modern v1 async client
    from openai import OpenAIError
except Exception:  # pragma: no cover - exercised when dependency missing

    class OpenAIError(Exception):
        pass

    class OpenAI:  # type: ignore[misc]
        """Minimal stub so tests can run without the openai package.

        Provides a no-op ``close`` and an ``audio.transcriptions.create``
        coroutine that raises a deterministic error when used.
        """

        class _Transcriptions:
            async def create(self, *_, **__):  # pragma: no cover - used only if a test hits it
                raise RuntimeError("offline_whisper_unavailable")

        class _Audio:
            def __init__(self) -> None:
                self.transcriptions = OpenAI._Transcriptions()

        def __init__(self, *_, **__):
            self.audio = OpenAI._Audio()

        async def close(self) -> None:
            return None


TRANSCRIBE_MODEL = os.getenv("OPENAI_TRANSCRIBE_MODEL", "whisper-1")

logger = logging.getLogger(__name__)
_client: OpenAI | None = None


def get_whisper_client() -> OpenAI:
    """Return a singleton OpenAI client with runtime API key lookup."""

    global _client
    if _client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            # Offline local mode: use a stub that raises quickly; callers catch and pivot
            class _Stub(OpenAI):  # type: ignore
                def __init__(self, *a, **k):
                    pass

            _client = _Stub()  # type: ignore
        else:
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
    try:
        # Open file first so missing paths are reported even when the OpenAI
        # client is unavailable in the test environment.
        with open(path, "rb") as f:
            client = get_whisper_client()
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
    except RuntimeError as e:
        # If client is a stub (no API key), indicate offline mode for caller
        raise RuntimeError("offline_whisper_unavailable") from e
    except Exception as e:
        logger.debug("transcribe_file error: %s", e)
        raise RuntimeError(f"Failed to read or send {path!r}: {e}") from e

    text = getattr(resp, "text", None)
    if not text:
        raise ValueError("empty_transcription")

    logger.debug("transcribe_file success: %s", path)
    return text


class TranscriptionStream:
    """Handle live transcription over a WebSocket."""

    def __init__(self, ws: WebSocket) -> None:
        self.ws = ws
        self.session_id = uuid.uuid4().hex

    async def _iter_audio(self, first_msg: dict) -> AsyncIterator[bytes]:
        msg = first_msg
        if msg.get("bytes") and has_speech(msg["bytes"]):
            yield msg["bytes"]
        while True:
            try:
                msg = await self.ws.receive()
            except RuntimeError:
                return
            if msg.get("type") == "websocket.disconnect":
                return
            if "text" in msg and msg["text"] == "end":
                return
            chunk = msg.get("bytes")
            if chunk and has_speech(chunk):
                yield chunk

    async def process(self) -> None:
        await self.ws.accept()
        try:
            msg = await self.ws.receive()
        except RuntimeError:
            return
        if "text" in msg and msg["text"]:
            try:
                json.loads(msg["text"])
                msg = await self.ws.receive()
            except Exception:
                await self.ws.send_json({"error": "invalid metadata"})
                await self.ws.close()
                return
        session = PipecatSession()
        await session.start()
        try:
            async for text in session.stream(self._iter_audio(msg)):
                await self.ws.send_json({"text": text, "session_id": self.session_id})
        except Exception as e:  # pragma: no cover - best effort
            await self.ws.send_json({"error": str(e)})
        finally:
            await session.stop()
