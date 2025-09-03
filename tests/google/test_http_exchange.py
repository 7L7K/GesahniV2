import asyncio
import pytest
import httpx

from app.integrations.google.http_exchange import async_token_exchange
from app.integrations.google.errors import OAuthError


class DummyResponse:
    def __init__(self, status_code, json_data):
        self.status_code = status_code
        self._json = json_data

    def json(self):
        return self._json


class DummyAsyncClient:
    def __init__(self, resp: DummyResponse = None, raise_exc: Exception | None = None):
        self._resp = resp
        self._raise = raise_exc

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, *a, **k):
        if self._raise:
            raise self._raise
        return self._resp


@pytest.mark.asyncio
async def test_exchange_success(monkeypatch):
    resp = DummyResponse(200, {"access_token": "at", "expires_in": 3600})

    async def _client(*a, **k):
        return DummyAsyncClient(resp)

    monkeypatch.setattr(
        "app.integrations.google.http_exchange.httpx.AsyncClient",
        lambda timeout: DummyAsyncClient(resp),
    )

    td = await async_token_exchange("code123", code_verifier="v" * 43)
    assert td.get("access_token") == "at"


@pytest.mark.asyncio
async def test_exchange_invalid_grant(monkeypatch):
    resp = DummyResponse(
        400, {"error": "invalid_grant", "error_description": "expired"}
    )
    monkeypatch.setattr(
        "app.integrations.google.http_exchange.httpx.AsyncClient",
        lambda timeout: DummyAsyncClient(resp),
    )

    with pytest.raises(OAuthError) as ei:
        await async_token_exchange("code123", code_verifier="v" * 43)
    e = ei.value
    assert e.code == "oauth_invalid_grant"


@pytest.mark.asyncio
async def test_exchange_timeout(monkeypatch):
    exc = httpx.TimeoutException("timeout")
    monkeypatch.setattr(
        "app.integrations.google.http_exchange.httpx.AsyncClient",
        lambda timeout: DummyAsyncClient(raise_exc=exc),
    )

    with pytest.raises(OAuthError) as ei:
        await async_token_exchange("code123", code_verifier="v" * 43, timeout=0.01)
    e = ei.value
    assert e.reason == "timeout"
