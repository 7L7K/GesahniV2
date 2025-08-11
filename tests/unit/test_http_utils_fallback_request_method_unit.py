import pytest


@pytest.mark.asyncio
async def test_json_request_fallback_method(monkeypatch):
    from app import http_utils

    class Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"ok": True}

    class Client:
        # intentionally no .request attribute
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, **kwargs):
            return Resp()

    monkeypatch.setattr(http_utils.httpx, "AsyncClient", lambda: Client())
    data, err = await http_utils.json_request("GET", "https://x/y")
    assert data == {"ok": True} and err is None


