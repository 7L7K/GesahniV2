import asyncio
from typing import Dict

_metrics = {"total": 0, "llama": 0, "gpt": 0, "fallback": 0}
_lock = asyncio.Lock()


async def record(engine: str, fallback: bool = False) -> None:
    async with _lock:
        _metrics["total"] += 1
        if engine == "llama":
            _metrics["llama"] += 1
        else:
            _metrics["gpt"] += 1
        if fallback:
            _metrics["fallback"] += 1


def get_metrics() -> Dict[str, int]:
    return _metrics.copy()
