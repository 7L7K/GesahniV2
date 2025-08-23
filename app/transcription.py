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
from collections.abc import AsyncIterator

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
        self._last_partial_ts: float = 0.0
        self._silence_started: float | None = None
        self._partial_min_interval_s: float = float(os.getenv("STT_PARTIAL_MIN_INTERVAL_S", "0.15") or 0.15)
        self._silence_final_s: float = float(os.getenv("STT_SILENCE_FINALIZE_S", "1.2") or 1.2)

    async def _iter_audio(self, first_msg: dict) -> AsyncIterator[bytes]:
        msg = first_msg
        # Gate audio by wake/PTT when configured
        wake_mode = os.getenv("WAKE_MODE", "any").lower()
        waiting = wake_mode in {"wake", "ptt", "both"}
        if msg.get("bytes") and has_speech(msg["bytes"]) and not waiting:
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
            if waiting:
                # Await a JSON control message indicating wake/PTT
                ctl = msg.get("text")
                if ctl:
                    try:
                        data = json.loads(ctl)
                        ptt_ok = bool(data.get("ptt"))
                        wake_ok = bool(data.get("wake"))
                        if wake_mode == "wake" and wake_ok:
                            waiting = False
                        elif wake_mode == "ptt" and ptt_ok:
                            waiting = False
                        elif wake_mode == "both" and wake_ok and ptt_ok:
                            waiting = False
                        elif wake_mode == "any" and (wake_ok or ptt_ok):
                            waiting = False
                    except Exception:
                        pass
                continue
            if chunk and has_speech(chunk):
                # reset silence window
                self._silence_started = None
                yield chunk
            else:
                # track silence onset
                if self._silence_started is None:
                    try:
                        import time as _t
                        self._silence_started = _t.time()
                    except Exception:
                        self._silence_started = None

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
        # Voice feature flag
        if os.getenv("VOICE_ENABLED", "1").lower() not in {"1", "true", "yes", "on"}:
            await self.ws.send_json({"error": "voice_disabled"})
            await self.ws.close()
            return

        async def emit(kind: str, payload: dict) -> None:
            try:
                await self.ws.send_json({"event": kind, **payload, "session_id": self.session_id})
            except Exception:
                pass

        try:
            session = PipecatSession(event_cb=emit)
        except TypeError:
            # Back-compat for tests that stub PipecatSession without kwargs
            session = PipecatSession()  # type: ignore
        await session.start()
        try:
            # Send initial listening state
            await self.ws.send_json({"event": "stt.state", "state": "listening", "session_id": self.session_id})
            last_text: str | None = None
            import time as _t
            async for text in session.stream(self._iter_audio(msg)):
                # Emit partials throttled; relay TTS sync markers out-of-band.
                now = _t.time()
                if now - self._last_partial_ts >= self._partial_min_interval_s:
                    await self.ws.send_json({"event": "stt.partial", "text": text, "session_id": self.session_id})
                    self._last_partial_ts = now
                last_text = text
                # End-of-speech via silence window
                if self._silence_started and (now - self._silence_started) >= self._silence_final_s:
                    break
            # Final punctuation pass (simple heuristic)
            try:
                import re as _re
                final_text = _re.sub(r"\s+", " ", (last_text or "")).strip()
                if final_text and final_text[-1] not in ".?!":
                    final_text += "."
            except Exception:
                final_text = last_text or ""
            await self.ws.send_json({"event": "stt.final", "text": final_text, "session_id": self.session_id})
        except Exception:  # pragma: no cover - best effort
            await self.ws.send_json({"error": "listening_network_shaky"})
        finally:
            await session.stop()
