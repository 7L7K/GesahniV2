import logging


def test_request_id_filter_uses_context_var():
    from app.logging_config import RequestIdFilter, req_id_var

    req_id_var.set("abc123")
    rec = logging.LogRecord("n", logging.INFO, __file__, 1, "m", (), None)
    RequestIdFilter().filter(rec)
    assert getattr(rec, "req_id", None) == "abc123"


