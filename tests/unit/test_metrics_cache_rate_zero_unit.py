from app import analytics as metrics


def test_cache_hit_rate_zero_division_safe():
    # Fresh process state might have zeros; ensure safe
    rate = metrics.cache_hit_rate()
    assert rate == 0.0


