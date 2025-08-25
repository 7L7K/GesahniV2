from __future__ import annotations
"""OpenVoice/Piper text-to-speech adapter.

This module defines the :class:`VoiceSynth` interface for cloning voices and
synthesizing speech. The actual model loading and synthesis are intentionally
left unimplemented; this is only the API surface.
"""


import logging
from pathlib import Path

_logger = logging.getLogger(__name__)  # noqa: F401  (reserved for future debug)


class VoiceSynth:
    """Basic interface for text-to-speech synthesis."""

    def __init__(self, voice_profile_path: str):
        """Initialize the synthesizer.

        Parameters
        ----------
        voice_profile_path:
            Path to a ``.pt`` file containing the speaker profile or embedding.
        """
        self.voice_profile_path = Path(voice_profile_path)

    def speak(self, text: str, *, style: dict | None = None) -> bytes:
        """Return WAV audio bytes for ``text``.

        ``style`` may include parameters like pitch or rate. This stub does not
        perform any synthesis.
        """
        raise NotImplementedError("Voice synthesis not implemented yet")


__all__ = ["VoiceSynth"]
