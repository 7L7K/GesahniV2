import os
import time

import jwt

from app.security import jwt_decode


def test_jwt_decode_respects_leeway(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "testsecret123456789012345678901234")
    # exp 30 seconds in the past, iat similarly
    now = int(time.time())
    payload = {"sub": "u1", "iat": now - 120, "exp": now - 30}
    token = jwt.encode(payload, os.getenv("JWT_SECRET"), algorithm="HS256")

    # With default leeway=60 the token should still decode
    claims = jwt_decode(token, os.getenv("JWT_SECRET"), algorithms=["HS256"])
    assert claims["sub"] == "u1"

    # With leeway=0 it should fail
    try:
        jwt_decode(token, os.getenv("JWT_SECRET"), algorithms=["HS256"], leeway=0)
        raise AssertionError("expected ExpiredSignatureError")
    except jwt.ExpiredSignatureError:
        pass
