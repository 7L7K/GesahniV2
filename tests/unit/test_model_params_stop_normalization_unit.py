def test_stop_normalization_iterables(monkeypatch):
    from app import model_params as mp

    merged = mp.merge_params({"stop": {"A", "", "B"}})
    assert sorted(merged["stop"]) == ["A", "B"]

    merged2 = mp.merge_params({"stop": ["x", "y"]})
    assert merged2["stop"] == ["x", "y"]


