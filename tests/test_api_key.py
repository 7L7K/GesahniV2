from importlib import reload

import pytest

from app import gpt_client

# Async test relies on pytest-asyncio to provide an event loop


def test_get_client_missing_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    gpt_client._client = None
    with pytest.raises(RuntimeError):
        gpt_client.get_client()


@pytest.mark.asyncio
async def test_close_client_double(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    reload(gpt_client)
    gpt_client.get_client()
    await gpt_client.close_client()
    await gpt_client.close_client()
