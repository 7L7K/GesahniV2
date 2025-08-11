def test_start_span_noop_without_otel(monkeypatch):
    from app import otel_utils

    # Force optional import path to look like not installed
    monkeypatch.setattr(otel_utils, "_trace", None)

    with otel_utils.start_span("x", {"a": 1}) as span:
        assert span is None

    # Methods should handle None safely
    otel_utils.set_error(None, RuntimeError("x"))
    assert otel_utils.get_trace_id_hex() in ("",)


