import asyncio
import math
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

_latency_samples: list[int] = []
_MAX_SAMPLES = 200


async def record(engine: str, fallback: bool = False, source: str = "gpt") -> None:
    async with _lock:
        _metrics["total"] += 1
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


async def record_latency(duration_ms: int) -> None:
    async with _lock:
        _latency_samples.append(max(duration_ms, 0))
        if len(_latency_samples) > _MAX_SAMPLES:
            _latency_samples.pop(0)


def latency_p95() -> int:
    if not _latency_samples:
        return 0
    samples = sorted(_latency_samples)
    idx = math.ceil(0.95 * len(samples)) - 1
    return samples[idx]
