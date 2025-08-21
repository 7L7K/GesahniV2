import pytest

from app import gpt_client
from app.telemetry import LogRecord, log_record_var


class _Usage:
    prompt_tokens = 1000
    completion_tokens = 2000


class _Resp:
    choices = [type("C", (), {"message": type("M", (), {"content": "hi"})()})]
    usage = _Usage()


class _Completions:
    async def create(self, *args, **kwargs):
        return _Resp()


class _Chat:
    completions = _Completions()


class _Client:
    chat = _Chat()


@pytest.mark.asyncio
async def test_cost_breakdown(monkeypatch):
    monkeypatch.setattr(gpt_client, "_TEST_MODE", False)
    monkeypatch.setattr(gpt_client, "get_client", lambda: _Client())
    rec = LogRecord(req_id="1")
    token = log_record_var.set(rec)
    try:
        _, pt, ct, cost = await gpt_client.ask_gpt("hi", model="gpt-4o", routing_decision=None)
    finally:
        log_record_var.reset(token)
    assert pt == 1000
    assert ct == 2000
    assert cost == pytest.approx(0.035)
    assert rec.prompt_cost_usd == pytest.approx(0.005)
    assert rec.completion_cost_usd == pytest.approx(0.03)
    assert rec.cost_usd == pytest.approx(0.035)
