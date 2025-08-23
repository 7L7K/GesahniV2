import asyncio
import logging
import tempfile
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path

from ... import router
from ...transcribe import has_speech, transcribe_file

logger = logging.getLogger(__name__)


class PipecatSession:
    """Minimal adapter for a Pipecat-style voice session.

    It bridges audio input, the main router/LLM, and an internal TTS hook.  The
    implementation here is intentionally lightweight for tests and examples – it
    does **not** attempt to integrate the real Pipecat stack but mirrors the
    interface expected by the application.
    """

    def __init__(
        self,
        stt: str = "whisper",
        tts: str = "piper",
        llm: str = "gpt-4o-mini",
        event_cb: Callable[[str, dict], Awaitable[None]] | None = None,
    ):
        self.stt = stt
        self.tts = tts
        self.llm = llm
        self._started = False
        self._event_cb = event_cb

    async def start(self) -> None:
        self._started = True
        logger.debug(
            "PipecatSession started stt=%s tts=%s llm=%s", self.stt, self.tts, self.llm
        )

    async def stop(self) -> None:
        self._started = False
        logger.debug("PipecatSession stopped")

    async def _speak(self, text: str) -> None:
        """TTS hook via orchestrator (logs in tests)."""
        if not text:
            return
        try:
            from ..tts_orchestrator import synthesize

            # Emit caption sync markers via logging hook for WS relay
            if self._event_cb is not None:
                try:
                    await self._event_cb("tts.start", {"engine": self.tts})
                except Exception:
                    pass
            audio = await synthesize(text=text, mode="capture")
            # In a real session we'd stream audio bytes to the client.
            # Here we only log for observability in tests.
            logger.debug("[TTS:%s] bytes=%d", self.tts, len(audio))
            if self._event_cb is not None:
                try:
                    await self._event_cb("tts.stop", {"engine": self.tts})
                except Exception:
                    pass
        except Exception:
            logger.debug("[TTS:%s] %s", self.tts, text)

    async def stream(self, audio_chunks: AsyncIterator[bytes]) -> AsyncIterator[str]:
        """Yield partial transcriptions then final LLM output.

        Args:
            audio_chunks: Raw PCM chunks from the client.
        Yields:
            Partial STT captions followed by the model's response tokens.
        """

        if not self._started:
            await self.start()

        buffer = bytearray()
        transcript = ""

        async for chunk in audio_chunks:
            if not has_speech(chunk):
                continue
            buffer.extend(chunk)
            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
                Path(tmp.name).write_bytes(buffer)
                try:
                    text = await asyncio.to_thread(transcribe_file, tmp.name)
                except Exception as exc:  # pragma: no cover - best effort
                    logger.debug("STT failed: %s", exc)
                    continue
            if text and text != transcript:
                transcript = text
                yield transcript

        # Hand final transcript to router/LLM and speak deltas
        queue: asyncio.Queue[str | None] = asyncio.Queue()

        async def _hook(token: str) -> None:
            if self._event_cb is not None:
                try:
                    await self._event_cb("llm.token", {"token": token})
                except Exception:
                    pass
            await queue.put(token)

        async def _run() -> None:
            try:
                await router.route_prompt(
                    transcript,
                    user_id="voice",
                    stream_cb=_hook,
                    stream_hook=self._speak,
                )
            finally:
                await queue.put(None)

        task = asyncio.create_task(_run())

        while True:
            tok = await queue.get()
            if tok is None:
                break
            yield tok

        await task
