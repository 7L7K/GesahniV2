"""
Voice pipeline for Granny Mode.

Subpackages:
- input: wake word, PTT driver, VAD, mic controller
- stt: offline-first STT with cloud fallback and partials
- nlp: intent routing and confirmation heuristics
- tts: text-to-speech engines
"""

__all__ = ["input", "stt", "nlp", "tts"]


