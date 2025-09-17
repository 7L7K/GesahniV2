import os
import time

import jwt
import pytest

ALGS = tuple((os.getenv("JWT_ALGS") or "HS256").split(","))
SECRET = os.getenv(
    "JWT_SECRET",
    "your-secure-jwt-secret-at-least-32-characters-long-please-change-this-in-production",
)
ISS = os.getenv("JWT_ISS") or os.getenv("JWT_ISSUER") or "tests"


def _make_claims(*, sub="test-user", scopes=None, minutes=15):
    now = int(time.time())
    claims = {
        "sub": sub,
        "iat": now,
        "exp": now + minutes * 60,
        "scope": " ".join(scopes or []),
    }
    # Only include issuer if it's configured
    if ISS and ISS != "tests":
        claims["iss"] = ISS
    return claims


@pytest.fixture
def bearer_auth():
    def _mk(scopes=None):
        token = jwt.encode(_make_claims(scopes=scopes or []), SECRET, algorithm=ALGS[0])
        return {"Authorization": f"Bearer {token}"}

    return _mk
