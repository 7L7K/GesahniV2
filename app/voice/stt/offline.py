"""Offline STT engine placeholder.

Implement a local model-based STT here (e.g., Vosk, Whisper.cpp).
For now, this is a stub returning an empty transcript.
"""

from collections.abc import Iterable


def transcribe_chunks(audio_chunks: Iterable[bytes]) -> str:
    return ""
