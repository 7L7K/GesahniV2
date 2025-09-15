import os

import jwt
import pytest

# Optional dependency: freezegun. Fallback to no-op if unavailable.
try:
    from freezegun import freeze_time  # type: ignore
except Exception:  # pragma: no cover - environment without freezegun

    def freeze_time(*args, **kwargs):  # type: ignore
        def _wrap(fn):
            return fn

        return _wrap


def _decode(token: str):
    """Decode using centralized helper when available; else HS256 with env secret."""
    try:
        from app.tokens import decode_jwt_token as _decode_jwt

        return _decode_jwt(token)
    except Exception:
        secret = os.getenv("JWT_SECRET", "test_secret_for_decode_fallback_32_chars_min")
        return jwt.decode(token, secret, algorithms=["HS256"])  # type: ignore[arg-type]


@pytest.fixture(autouse=True)
def _std_env(monkeypatch):
    # Deterministic, long-enough secret for HS256
    monkeypatch.setenv(
        "JWT_SECRET", "unit_test_secret_abcdefghijklmnopqrstuvwxyz123456"
    )
    # Deterministic TTLs for unit tests unless a test overrides
    monkeypatch.setenv("JWT_ACCESS_TTL_SECONDS", "1200")  # 20 minutes
    monkeypatch.setenv("JWT_REFRESH_TTL_SECONDS", "7200")  # 120 minutes
    # Disable audience/issuer unless a test enables for contract assertions
    monkeypatch.delenv("JWT_ISS", raising=False)
    monkeypatch.delenv("JWT_AUD", raising=False)


@freeze_time("2025-01-01 12:00:00", tz_offset=0)
def test_make_access_includes_contract_shape():
    from app.tokens import make_access

    token = make_access({"user_id": "u1"})
    claims = _decode(token)

    # Identity mapping
    assert claims["sub"] == "u1"
    assert claims["user_id"] == "u1"

    # Contract fields
    assert isinstance(claims["iat"], int) or isinstance(claims["iat"], float)
    assert isinstance(claims["exp"], int) or isinstance(claims["exp"], float)
    assert claims["type"] == "access"
    assert claims["scopes"] and isinstance(claims["scopes"], list)

    # TTL = 1200s from env
    iat = int(claims["iat"])  # epoch
    exp = int(claims["exp"])  # epoch
    assert exp - iat == 1200


@freeze_time("2025-01-01 12:00:00", tz_offset=0)
def test_make_refresh_includes_contract_shape_and_jti():
    from app.tokens import make_refresh

    token = make_refresh({"user_id": "u2"})
    claims = _decode(token)

    assert claims["sub"] == "u2"
    assert claims["user_id"] == "u2"
    assert claims["type"] == "refresh"
    assert claims.get("jti") and isinstance(claims["jti"], str)

    # TTL = 7200s from env
    assert int(claims["exp"]) - int(claims["iat"]) == 7200


def test_normalizes_user_id_and_sub_both_directions():
    from app.tokens import make_access

    # Only user_id provided
    t1 = make_access({"user_id": "alice"})
    c1 = _decode(t1)
    assert c1["sub"] == "alice" and c1["user_id"] == "alice"

    # Only sub provided
    t2 = make_access({"sub": "bob"})
    c2 = _decode(t2)
    assert c2["sub"] == "bob" and c2["user_id"] == "bob"


def test_custom_scopes_override_defaults():
    from app.tokens import make_access

    t = make_access({"user_id": "u", "scopes": ["chat:write", "admin:read"]})
    c = _decode(t)
    assert set(c["scopes"]) == {"chat:write", "admin:read"}


def test_decode_jwt_token_matches_pyjwt(monkeypatch):
    from app.tokens import decode_jwt_token, make_access

    token = make_access({"user_id": "u"})
    claims = decode_jwt_token(token)

    # Independently decode with HS256 to cross-check shape
    secret = os.environ["JWT_SECRET"]
    claims2 = jwt.decode(token, secret, algorithms=["HS256"])  # type: ignore[arg-type]
    # Minimal contract equality
    for k in ["sub", "user_id", "type"]:
        assert claims[k] == claims2[k]


@freeze_time("2025-01-01 12:00:00", tz_offset=0)
def test_sign_access_token_ttl_override(monkeypatch):
    from app.tokens import sign_access_token

    tok = sign_access_token("u3", extra={"ttl_override": 15, "foo": "bar"})
    c = _decode(tok)
    assert c["sub"] == "u3"
    assert c["foo"] == "bar"
    assert int(c["exp"]) - int(c["iat"]) == 15 * 60


def test_get_default_access_ttl_reflects_env(monkeypatch):
    from app.tokens import get_default_access_ttl

    # Override to a distinct value
    monkeypatch.setenv("JWT_ACCESS_TTL_SECONDS", "1337")
    assert get_default_access_ttl() == 1337


def test_hs256_headers_have_no_kid_by_default():
    from jwt import get_unverified_header

    from app.tokens import make_access

    tok = make_access({"user_id": "kidless"})
    header = get_unverified_header(tok)
    # HS256 with shared secret should not include kid
    assert "kid" not in header
