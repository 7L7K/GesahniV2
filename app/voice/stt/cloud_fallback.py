"""Offline-first STT with cloud fallback wrapper."""

from typing import Iterable

from .offline import transcribe_chunks as offline_transcribe

try:
    from ...transcription import transcribe_file as cloud_transcribe  # type: ignore
except Exception:  # pragma: no cover - optional
    cloud_transcribe = None  # type: ignore


def transcribe_with_fallback(file_path: str, *, prefer_offline: bool = True) -> str:
    if prefer_offline:
        try:
            # In a real implementation we would stream chunks; placeholder uses file fallback
            text = offline_transcribe([])
            if text:
                return text
        except Exception:
            pass
    if cloud_transcribe is None:
        return ""
    try:
        import asyncio

        return asyncio.get_event_loop().run_until_complete(cloud_transcribe(file_path))
    except Exception:
        return ""


