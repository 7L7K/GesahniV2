def test_latency_samples_trim():
    from app import analytics as metrics
    import asyncio
    async def _run():
        for i in range(300):
            await metrics.record_latency(i)
    asyncio.run(_run())
    samples = metrics.get_latency_samples()
    assert len(samples) <= 200


