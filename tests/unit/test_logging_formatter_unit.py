import json
import logging


def test_json_formatter_and_request_id_filter():
    from app.logging_config import JsonFormatter, RequestIdFilter

    formatter = JsonFormatter()

    rec = logging.LogRecord(
        name="comp", level=logging.INFO, pathname=__file__, lineno=1, msg="hello", args=(), exc_info=None
    )
    rec.meta = {"x": 1}

    # ensure filter populates req_id so formatter includes it
    RequestIdFilter().filter(rec)
    s = formatter.format(rec)
    data = json.loads(s)
    assert data["msg"] == "hello" and data["component"] == "comp"
    assert "req_id" in data


