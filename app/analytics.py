import asyncio
from typing import Dict

_metrics = {
    "total": 0,
    "llama": 0,
    "gpt": 0,
    "fallback": 0,
    "session_count": 0,
    "transcribe_ms": 0,
    "transcribe_count": 0,
    "transcribe_errors": 0,
}
_lock = asyncio.Lock()


async def record(engine: str, fallback: bool = False, source: str = "gpt") -> None:
    async with _lock:
        _metrics["total"] += 1
        if source == "gpt":
            if engine == "llama":
                _metrics["llama"] += 1
            elif engine == "gpt":
                _metrics["gpt"] += 1
        if fallback:
            _metrics["fallback"] += 1


async def record_session() -> None:
    async with _lock:
        _metrics["session_count"] += 1


async def record_transcription(duration_ms: int, error: bool = False) -> None:
    async with _lock:
        _metrics["transcribe_count"] += 1
        _metrics["transcribe_ms"] += max(duration_ms, 0)
        if error:
            _metrics["transcribe_errors"] += 1


def get_metrics() -> Dict[str, int]:
    return _metrics.copy()
