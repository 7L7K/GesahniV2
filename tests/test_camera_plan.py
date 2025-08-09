import asyncio

from app.model_router import route_vision


def test_camera_plan_low_risk():
    async def ask_stub(prompt, model, system, **kwargs):
        return "ok", 0, 0, 0.0

    model, reason = asyncio.run(route_vision(ask_func=ask_stub, images=[b"f"], text_hint="cat"))
    assert model == "gpt-4o-mini"
    assert reason.startswith("vision-")


def test_camera_plan_high_risk_safety_retry():
    calls = []

    async def ask_stub(prompt, model, system, **kwargs):
        calls.append(model)
        return "ok", 0, 0, 0.0

    model, reason = asyncio.run(route_vision(ask_func=ask_stub, images=[b"f"], text_hint="stove fire"))
    assert model == "gpt-4o"  # safety retry
    assert reason in {"vision-high", "vision-safety"}
    assert "gpt-4o-mini" in calls and "gpt-4o" in calls

