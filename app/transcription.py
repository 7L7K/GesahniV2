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
from pathlib import Path

from fastapi import HTTPException, WebSocket, WebSocketDisconnect

from .session_manager import SESSIONS_DIR

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


class TranscriptionStream:
    """Handle live transcription over a WebSocket."""

    async def process(self) -> None:
        await self.ws.accept()
        # initial handshake
        try:
            msg = await self.ws.receive()
        except RuntimeError:
            return

        # skip initial metadata if present
        if "text" in msg and msg["text"]:
            try:
                json.loads(msg["text"])
            except Exception:
                await self.ws.send_json({"error": "invalid metadata"})
                await self.ws.close()
                return
            try:
                msg = await self.ws.receive()
            except RuntimeError:
                return

        tmp = self.audio_path.with_suffix(".part")
        with open(self.audio_path, "ab") as fh:
            while True:
                # catch disconnects
                try:
                    msg = await self.ws.receive()
                except RuntimeError:
                    break

                if msg.get("type") == "websocket.disconnect":
                    break
                if "text" in msg and msg["text"] == "end":
                    break

                chunk = msg.get("bytes")
                if not chunk:
                    continue

                fh.write(chunk)
                tmp.write_bytes(chunk)
                try:
                    text = await transcribe_file(str(tmp))
                    self.full_text += (" " if self.full_text else "") + text
                    await self.ws.send_json({
                        "text": self.full_text,
                        "session_id": self.session_id
                    })
                except Exception as e:
                    await self.ws.send_json({"error": str(e)})
                finally:
                    if tmp.exists():
                        tmp.unlink()