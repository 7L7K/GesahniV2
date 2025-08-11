import pytest


@pytest.mark.asyncio
async def test_apply_rate_limit_and_pruning(monkeypatch):
    from app import security as sec

    # high limit to avoid dependence on env
    monkeypatch.setenv("RATE_LIMIT_PER_MIN", "100")
    sec._requests.clear()

    assert await sec._apply_rate_limit("ip")
    assert await sec._apply_rate_limit("ip")

    # prune-only path leaves entries intact
    assert await sec._apply_rate_limit("ip", record=False)
    assert "ip" in sec._requests


