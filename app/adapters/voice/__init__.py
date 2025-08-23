"""Voice synthesis adapters."""

from .openvoice_adapter import VoiceSynth

# Testing placeholder metrics to satisfy imports in piper/openai TTS modules
try:
    # If the real metrics module exists, this import will succeed
    from .metrics import TTS_COST_USD, TTS_LATENCY_SECONDS, TTS_REQUEST_COUNT  # type: ignore
except Exception:  # pragma: no cover
    class _Noop:
        def inc(self, *a, **k):
            pass

        def observe(self, *a, **k):
            pass

    TTS_REQUEST_COUNT = _Noop()
    TTS_LATENCY_SECONDS = _Noop()
    TTS_COST_USD = _Noop()

__all__ = ["VoiceSynth", "TTS_REQUEST_COUNT", "TTS_LATENCY_SECONDS", "TTS_COST_USD"]
