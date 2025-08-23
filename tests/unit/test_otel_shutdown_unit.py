from __future__ import annotations


def test_shutdown_tracing_no_sdk(monkeypatch):
    import app.otel_utils as ot

    # Simulate environment without OpenTelemetry installed
    monkeypatch.setattr(ot, "_trace", None, raising=True)
    # Should not raise
    ot.shutdown_tracing()


def test_shutdown_tracing_calls_provider_and_processor(monkeypatch):
    import app.otel_utils as ot

    class _FakeProcessor:
        def __init__(self):
            self.calls = []

        def shutdown(self, *args, **kwargs):  # noqa: D401 - test stub
            self.calls.append((args, kwargs))

    class _FakeProvider:
        def __init__(self, processor):
            self._active_span_processor = processor
            self.shutdown_called = 0

        def shutdown(self):  # noqa: D401 - test stub
            self.shutdown_called += 1

    class _FakeTrace:
        def __init__(self, provider):
            self._provider = provider

        def get_tracer_provider(self):  # noqa: D401 - test stub
            return self._provider

    processor = _FakeProcessor()
    provider = _FakeProvider(processor)
    fake_trace = _FakeTrace(provider)

    # Patch the module-level _trace used by shutdown_tracing
    monkeypatch.setattr(ot, "_trace", fake_trace, raising=True)

    ot.shutdown_tracing(timeout_millis=10)

    # Processor shutdown was attempted (with timeout fallback handling)
    assert len(processor.calls) >= 1
    # Provider shutdown was called (idempotent and safe)
    assert provider.shutdown_called >= 1
