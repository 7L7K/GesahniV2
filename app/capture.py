"""Audio capture utilities."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

try:
    import sounddevice as sd
except Exception:  # pragma: no cover - optional dependency
    sd = None
from scipy.io import wavfile


logger = logging.getLogger(__name__)


async def record(duration: float, output: str) -> Path:
    """Record microphone input for ``duration`` seconds and save to ``output``.

    Parameters
    ----------
    duration:
        Number of seconds to capture.
    output:
        Destination WAV filename.
    """

    if sd is None:
        raise RuntimeError("sounddevice unavailable")

    path = Path(output)
    logger.info(
        "capture_start", extra={"meta": {"duration": duration, "path": str(path)}}
    )
    fs = 44100
    try:
        data = await asyncio.to_thread(
            sd.rec, int(duration * fs), samplerate=fs, channels=1, dtype="float32"
        )
        await asyncio.to_thread(sd.wait)
        await asyncio.to_thread(wavfile.write, path, fs, data)
        logger.info("capture_saved", extra={"meta": {"path": str(path)}})
        return path
    except Exception as e:  # pragma: no cover - unexpected
        logger.exception("capture_failed: %s", e)
        raise


__all__ = ["record"]

