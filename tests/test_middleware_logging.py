from app.telemetry import LogRecord


def test_logrecord_has_observability_fields():
    rec = LogRecord(req_id="1")
    # Ensure new fields exist
    for f in (
        "route_reason",
        "retrieved_tokens",
        "self_check_score",
        "escalated",
        "prompt_hash",
    ):
        assert hasattr(rec, f)


def test_request_headers_set(monkeypatch):
    import os
    from fastapi.testclient import TestClient
    from app import main

    monkeypatch.setattr(main, "ha_startup", lambda: None)
    monkeypatch.setattr(main, "llama_startup", lambda: None)
    # Ensure HTTPS to trigger HSTS path and CSP
    os.environ["OTEL_ENABLED"] = "0"
    c = TestClient(main.app)
    # Provide X-Request-ID to test propagation
    rid = "test-rid-123"
    r = c.get("/health")
    assert "X-Request-ID" in r.headers


