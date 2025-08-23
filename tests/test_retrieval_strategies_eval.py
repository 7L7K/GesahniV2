from __future__ import annotations

from app.retrieval.strategies import reciprocal_rank_fusion, temporal_boost_order, time_decay


def test_rrf_merges_lists_reasonably():
    a = ["a", "b", "c", "d"]
    b = ["b", "a", "e", "f"]
    fused = reciprocal_rank_fusion([a, b], k=60)
    # top two should be a/b in some order
    assert set(fused[:2]) == {"a", "b"}


def test_time_decay_monotonic():
    assert time_decay(0.0) >= time_decay(10.0)
    assert 0.0 <= time_decay(1000.0) <= 1.0


def test_temporal_boost_changes_order():
    scores = [0.8, 0.79]
    ages = [1000.0, 1.0]
    # Without boost, index 0 is higher; with boost, recent (index 1) can win
    order = temporal_boost_order(scores, ages, alpha=0.2)
    assert order[0] in {0, 1}
    # Crank alpha enough to flip
    order2 = temporal_boost_order(scores, ages, alpha=0.9)
    assert order2[0] == 1


