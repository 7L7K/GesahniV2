import os
import asyncio


def test_vision_quota_concurrency(monkeypatch):
    os.environ["VISION_MAX_IMAGES_PER_DAY"] = "2"
    from app import model_router as mr

    # Reset internal counters
    mr._VISION_DAY = None
    mr._VISION_COUNT = 0

    async def fake_ask(images, text_hint=None, allow_test=False):
        return "gpt-4o-mini", "vision-remote"

    async def worker():
        model, reason = await mr.route_vision(ask_func=fake_ask, images=[b"x"], text_hint="ok")
        return reason

    # Run 3 concurrent; only first two should pass cap
    async def run_all():
        return await asyncio.gather(worker(), worker(), worker())

    reasons = asyncio.run(run_all())
    assert reasons.count("vision-remote") >= 1
    assert reasons.count("vision-local-cap") >= 1


