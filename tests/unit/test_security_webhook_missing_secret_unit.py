import pytest


@pytest.mark.asyncio
async def test_verify_webhook_missing_secret(monkeypatch):
    from fastapi import Request

    from app.security.webhooks import verify_webhook

    # ensure no env/file secrets
    monkeypatch.delenv("HA_WEBHOOK_SECRETS", raising=False)
    monkeypatch.delenv("HA_WEBHOOK_SECRET", raising=False)
    monkeypatch.setenv("HA_WEBHOOK_SECRET_FILE", "nonexistent.txt")

    scope = {"type": "http", "method": "POST", "path": "/", "headers": []}
    req = Request(scope)
    with pytest.raises(Exception):
        await verify_webhook(req)
