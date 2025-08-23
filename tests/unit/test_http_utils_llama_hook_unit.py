import types

import pytest


@pytest.mark.asyncio
async def test_json_request_uses_llama_httpx(monkeypatch):
    from app import http_utils, llama_integration

    calls = {"used": False}

    class Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"ok": True}

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, **kwargs):
            calls["used"] = True
            return Resp()

    # Attach a fake httpx module to llama_integration
    fake_httpx = types.SimpleNamespace(AsyncClient=lambda: Client())
    monkeypatch.setattr(llama_integration, "httpx", fake_httpx, raising=False)

    data, err = await http_utils.json_request("GET", "https://x/y")
    assert data == {"ok": True} and err is None
    assert calls["used"] is True


