import pytest
from fastapi import HTTPException

from app.error_envelope import build_error, raise_enveloped


def test_build_error_contains_ids():
    env = build_error(code="bad_request", message="bad request")
    assert env["code"] == "bad_request"
    assert "details" in env
    d = env["details"]
    # error_id should always be present for correlation
    assert "error_id" in d
    assert "timestamp" in d


def test_raise_enveloped_raises_http_exception():
    with pytest.raises(HTTPException) as ei:
        raise_enveloped("not_allowed", "not allowed", status=403)
    exc = ei.value
    assert exc.status_code == 403
    assert isinstance(exc.detail, dict)
    assert exc.detail.get("code") == "not_allowed"
    # header X-Error-Code should be set on the exception
    assert exc.headers.get("X-Error-Code") == "not_allowed"
