import asyncio

import pytest


@pytest.mark.asyncio
async def test_record_and_snapshot():
    from app import analytics as metrics

    # ensure clean slate via internal copies
    before = metrics.get_metrics()
    await metrics.record("gpt")
    await metrics.record("llama", fallback=True)
    await metrics.record_session()
    await metrics.record_transcription(123)
    await metrics.record_transcription(50, error=True)
    await metrics.record_cache_lookup(hit=True)
    await metrics.record_cache_lookup(hit=False)
    await metrics.record_ha_failure()

    m = metrics.get_metrics()
    assert m["total"] == before["total"] + 2
    assert m["gpt"] >= before["gpt"] + 1
    assert m["llama"] >= before["llama"] + 1
    assert m["fallback"] >= before["fallback"] + 1
    assert m["session_count"] >= before["session_count"] + 1
    assert m["transcribe_count"] >= before["transcribe_count"] + 2
    assert m["transcribe_ms"] >= before["transcribe_ms"] + 173
    assert m["cache_lookups"] >= before["cache_lookups"] + 2
    assert m["cache_hits"] >= before["cache_hits"] + 1
    assert m["ha_failures"] >= before["ha_failures"] + 1


def test_latency_stats_and_top_skills():
    import importlib

    from app import analytics as metrics

    # reload to isolate samples for this test
    metrics = importlib.reload(metrics)

    # empty p95 -> 0
    assert metrics.latency_p95() == 0

    async def _run():
        for ms in [1, 5, 10, 20, 30, 40, 50, 60, 70, 80]:
            await metrics.record_latency(ms)
        await metrics.record_skill("a")
        await metrics.record_skill("a")
        await metrics.record_skill("b")

    asyncio.run(_run())

    p95 = metrics.latency_p95()
    assert isinstance(p95, int) and p95 >= 50

    top = metrics.get_top_skills(2)
    assert top[0][0] == "a" and top[0][1] >= 2

    rate = metrics.cache_hit_rate()
    assert 0.0 <= rate <= 100.0

    samples = metrics.get_latency_samples()
    assert isinstance(samples, list) and all(isinstance(x, int) for x in samples)


