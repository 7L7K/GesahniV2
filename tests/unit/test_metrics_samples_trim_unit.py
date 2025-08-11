import asyncio


def test_latency_samples_trim():
    from app import analytics as metrics

    async def _run():
        for i in range(300):
            await metrics.record_latency(i)

    asyncio.get_event_loop().run_until_complete(_run())
    samples = metrics.get_latency_samples()
    assert len(samples) <= 200


