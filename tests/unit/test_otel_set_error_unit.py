def test_set_error_on_span_stub():
    from app import otel_utils

    calls = {"record_exception": 0, "set_attr": 0}

    class Span:
        def record_exception(self, e):
            calls["record_exception"] += 1

        def set_attribute(self, k, v=None):
            calls["set_attr"] += 1

    otel_utils.set_error(Span(), RuntimeError("x"))
    assert calls["record_exception"] >= 1
    assert calls["set_attr"] >= 1


