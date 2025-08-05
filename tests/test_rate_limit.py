import asyncio
import time

import app.security as security


def test_rate_limit_prunes_empty(monkeypatch):
    monkeypatch.setattr(security, "_requests", {"ip": [time.time() - 120]})
    asyncio.run(security._apply_rate_limit("ip", record=False))
    assert "ip" not in security._requests
