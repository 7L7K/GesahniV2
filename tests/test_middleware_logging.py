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


