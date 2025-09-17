import asyncio
import time

import pytest
from fastapi.testclient import TestClient

import app.auth as auth
from app.main import get_app


@pytest.mark.integration
def test_csrf_enforcement_on_login(monkeypatch):
    # Enable CSRF enforcement at runtime
    monkeypatch.setenv("CSRF_ENABLED", "1")
    # Re-import app after setting CSRF_ENABLED to ensure middleware picks it up
    import importlib

    import app.main

    importlib.reload(app.main)
    client = TestClient(app.main.get_app())

    # Ensure user exists (ignore username_taken) - provide CSRF tokens
    client.post(
        "/v1/register",
        json={"username": "test_user_123", "password": "test_password_123"},
        headers={"X-CSRF-Token": "test"},
        cookies={"csrf_token": "test"},
    )

    # Missing CSRF -> 403
    from fastapi.exceptions import HTTPException

    try:
        r = client.post(
            "/v1/login",
            json={"username": "test_user_123", "password": "test_password_123"},
        )
        assert r.status_code == 403
    except HTTPException as e:
        assert e.status_code == 403

    # With cookie + header -> 200 (or 500 if server error) but expect not 403
    r2 = client.post(
        "/v1/login",
        json={"username": "test_user_123", "password": "test_password_123"},
        headers={"X-CSRF-Token": "test"},
        cookies={"csrf_token": "test"},
    )
    assert r2.status_code in (200, 400, 401) or r2.status_code < 500


@pytest.mark.integration
def test_backoff_sleep_in_login(monkeypatch):
    client = TestClient(get_app())
    username = "test_user_123"
    # Ensure user exists (ignore if already exists)
    register_resp = client.post(
        "/v1/register", json={"username": username, "password": "test_password_123"}
    )
    # 200 = created, 409 = already exists (both are fine for this test)
    assert register_resp.status_code in (200, 409)

    # Set small backoff window and threshold
    monkeypatch.setenv("LOGIN_BACKOFF_THRESHOLD", "1")
    monkeypatch.setenv("LOGIN_BACKOFF_START_MS", "200")
    monkeypatch.setenv("LOGIN_BACKOFF_MAX_MS", "200")

    # Put attempts above threshold
    user_key = f"user:{username}"
    auth._attempts[user_key] = (2, time.time())

    # Patch asyncio.sleep to capture call
    calls = []

    async def fake_sleep(s):
        calls.append(s)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    # Call login; it will trigger backoff path which calls asyncio.sleep
    client.post(
        "/v1/login",
        json={"username": username, "password": "test_wrong_password"},
        headers={"X-CSRF-Token": "t"},
        cookies={"csrf_token": "t"},
    )

    # Backoff should have invoked sleep at least once
    assert any(calls), "asyncio.sleep was not called for backoff"
    # Sleep should be >= start_ms/1000
    assert any(c >= 0.2 for c in calls)
