def test_otel_disabled_env(monkeypatch):
    import app.otel_utils as ot

    monkeypatch.setenv("OTEL_ENABLED", "0")
    assert ot.init_tracing() is False
