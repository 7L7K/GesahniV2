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

    class DummyClient:
        def __init__(self, *args, **kwargs):
            self.closed = False

        async def close(self) -> None:
            self.closed = True

    reload(gpt_client)
    monkeypatch.setattr(gpt_client, "AsyncOpenAI", DummyClient)

    client = gpt_client.get_client()
    # Reusing the client should not create a new instance
    assert gpt_client.get_client() is client

    await gpt_client.close_client()
    assert client.closed
    assert gpt_client._client is None

    # Closing again should be a no-op
    await gpt_client.close_client()
