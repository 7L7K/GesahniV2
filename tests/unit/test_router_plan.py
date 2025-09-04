import os
from app.routers.config import build_plan

def names(plan): return [s.import_path for s in plan]

def test_ci_hides_optionals(monkeypatch):
    # Set CI=1 and clear optional flags
    monkeypatch.setenv("CI", "1")
    monkeypatch.delenv("SPOTIFY_ENABLED", raising=False)
    monkeypatch.delenv("APPLE_OAUTH_ENABLED", raising=False)
    monkeypatch.delenv("DEVICE_AUTH_ENABLED", raising=False)

    plan = names(build_plan())
    assert all("spotify" not in p for p in plan)
    assert all("oauth_apple" not in p for p in plan)
    assert all("auth_device" not in p for p in plan)

def test_dev_opt_in(monkeypatch):
    # Clear CI, pytest flag, and optional flags first
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.delenv("SPOTIFY_ENABLED", raising=False)
    monkeypatch.delenv("APPLE_OAUTH_ENABLED", raising=False)
    monkeypatch.delenv("DEVICE_AUTH_ENABLED", raising=False)

    # Test: no spotify by default
    assert all("spotify" not in p for p in names(build_plan()))

    # Test: enable spotify
    monkeypatch.setenv("SPOTIFY_ENABLED", "1")
    assert any("spotify" in p for p in names(build_plan()))
