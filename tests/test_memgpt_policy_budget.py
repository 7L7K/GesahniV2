from __future__ import annotations

from app.memory.memgpt.contracts import MemoryClaim
from app.memory.memgpt.policy import should_store


def test_policy_blocks_low_confidence():
    low = MemoryClaim(claim="x", evidence=["e"], confidence=0.3, horizons=["short"])
    high = MemoryClaim(claim="y", evidence=["e"], confidence=0.9, horizons=["long"])
    assert should_store(high)
    assert not should_store(low)
