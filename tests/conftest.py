"""Test-specific fixtures."""

import pytest


@pytest.fixture(autouse=True)
def _reset_llama_health(monkeypatch):
    """Ensure ``LLAMA_HEALTHY`` starts True for each test and silence OTEL."""
    from app import llama_integration

    llama_integration.LLAMA_HEALTHY = True
    # Silence OpenTelemetry exporter during tests to avoid noisy connection errors
    monkeypatch.setenv("OTEL_ENABLED", "0")
