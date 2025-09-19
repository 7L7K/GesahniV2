import time

import jwt


def test_decode_allows_clock_skew(monkeypatch):
    key = "x" * 64
    now = int(time.time())
    bad_iat = now + 30  # 30s in the future
    token = jwt.encode(
        {"sub": "u1", "iat": bad_iat, "exp": now + 3600}, key, algorithm="HS256"
    )
    monkeypatch.setenv("JWT_CLOCK_SKEW_S", "60")
    from app.security import jwt_decode

    assert jwt_decode(token, key, ["HS256"])["sub"] == "u1"
