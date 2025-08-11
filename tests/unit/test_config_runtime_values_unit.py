def test_config_parsing_types(monkeypatch):
    from app import config_runtime as cr

    monkeypatch.setenv("PYTEST_RUNNING", "1")
    monkeypatch.setenv("TOPK_VEC", "10")
    monkeypatch.setenv("TOPK_FINAL", "5")
    monkeypatch.setenv("USE_MMR", "true")
    monkeypatch.setenv("MMR_LAMBDA", "0.25")
    monkeypatch.setenv("RERANK_GATE_LOW", "0.1")
    monkeypatch.setenv("TRACE_SAMPLE_RATE", "0.5")
    monkeypatch.setenv("LATENCY_BUDGET_MS", "1000")
    monkeypatch.setenv("ABLATION_FLAGS", "a,b")

    cfg = cr.get_config()
    assert cfg.retrieval.topk_vec == 10
    assert cfg.retrieval.topk_final == 5
    assert cfg.retrieval.use_mmr is True
    assert abs(cfg.retrieval.mmr_lambda - 0.25) < 1e-6
    assert abs(cfg.rerank.gate_low - 0.1) < 1e-6
    assert abs(cfg.obs.trace_sample_rate - 0.5) < 1e-6
    assert cfg.obs.latency_budget_ms == 1000
    assert cfg.obs.ablation_flags == {"a", "b"}


