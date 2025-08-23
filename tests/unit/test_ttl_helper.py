from app.api.auth import _get_refresh_ttl_seconds


def test_refresh_ttl_seconds_env_seconds(monkeypatch):
    monkeypatch.setenv("JWT_REFRESH_TTL_SECONDS", "3600")
    monkeypatch.delenv("JWT_REFRESH_EXPIRE_MINUTES", raising=False)
    assert _get_refresh_ttl_seconds() == 3600


def test_refresh_ttl_minutes_fallback(monkeypatch):
    monkeypatch.delenv("JWT_REFRESH_TTL_SECONDS", raising=False)
    monkeypatch.setenv("JWT_REFRESH_EXPIRE_MINUTES", "30")
    assert _get_refresh_ttl_seconds() == 1800


def test_refresh_ttl_default(monkeypatch):
    for k in ("JWT_REFRESH_TTL_SECONDS", "JWT_REFRESH_EXPIRE_MINUTES"):
        monkeypatch.delenv(k, raising=False)
    # default 7 days
    assert _get_refresh_ttl_seconds() == 7 * 24 * 60 * 60
