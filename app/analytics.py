import asyncio
import math
from typing import Dict, List, Tuple

_metrics = {
    "total": 0,
    "llama": 0,
    "gpt": 0,
    "fallback": 0,
    "session_count": 0,
    "transcribe_ms": 0,
    "transcribe_count": 0,
    "transcribe_errors": 0,
    # Proactive/admin extras
    "cache_hits": 0,
    "cache_lookups": 0,
    "ha_failures": 0,
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


# -----------------------------
# Admin insight helpers
# -----------------------------

_skill_counts: Dict[str, int] = {}


async def record_skill(name: str) -> None:
    async with _lock:
        _skill_counts[name] = _skill_counts.get(name, 0) + 1


def get_top_skills(n: int = 10) -> List[Tuple[str, int]]:
    items = sorted(_skill_counts.items(), key=lambda kv: kv[1], reverse=True)
    return items[:n]


async def record_cache_lookup(hit: bool) -> None:
    async with _lock:
        # Ensure keys exist in case tests or earlier code mutated _metrics
        if "cache_lookups" not in _metrics:
            _metrics["cache_lookups"] = 0
        if "cache_hits" not in _metrics:
            _metrics["cache_hits"] = 0
        _metrics["cache_lookups"] += 1
        if hit:
            _metrics["cache_hits"] += 1


def cache_hit_rate() -> float:
    lookups = _metrics.get("cache_lookups", 0)
    hits = _metrics.get("cache_hits", 0)
    if lookups == 0:
        return 0.0
    return round(100.0 * hits / max(1, lookups), 2)


async def record_ha_failure() -> None:
    async with _lock:
        _metrics["ha_failures"] += 1


def get_latency_samples() -> List[int]:
    """Return a copy of the latency samples buffer (for diagnostics)."""
    return list(_latency_samples)
