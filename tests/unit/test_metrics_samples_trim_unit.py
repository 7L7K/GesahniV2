def test_latency_samples_trim():
    import asyncio

    from app import analytics as metrics

    async def _run():
        for i in range(300):
            await metrics.record_latency(i)

    asyncio.run(_run())
    samples = metrics.get_latency_samples()
    assert len(samples) <= 200
