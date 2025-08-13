import os
import jwt
from starlette.requests import Request


def test_get_request_payload_without_secret_decodes_without_verify(monkeypatch):
    import app.security as sec

    monkeypatch.delenv("JWT_SECRET", raising=False)
    tok = jwt.encode({"user_id": "uX"}, "ignored", algorithm="HS256")
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [(b"authorization", f"Bearer {tok}".encode())],
    }
    req = Request(scope)
    p = sec._get_request_payload(req)
    assert isinstance(p, dict)


