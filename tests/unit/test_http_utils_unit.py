import asyncio
import types
import pytest


@pytest.mark.asyncio
async def test_json_request_success(monkeypatch):
    from app import http_utils

    class Resp:
        def __init__(self):
            self._status = 200

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
            return Resp()

    # Patch AsyncClient with our stub
    monkeypatch.setattr(http_utils.httpx, "AsyncClient", lambda: Client())

    data, err = await http_utils.json_request("GET", "https://x/y")
    assert data == {"ok": True}
    assert err is None


@pytest.mark.asyncio
async def test_json_request_json_decode_error(monkeypatch):
    from app import http_utils

    class Resp:
        def raise_for_status(self):
            return None

        def json(self):
            raise ValueError("bad json")

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, **kwargs):
            return Resp()

    monkeypatch.setattr(http_utils.httpx, "AsyncClient", lambda: Client())

    data, err = await http_utils.json_request("GET", "https://x/y")
    assert data is None and err == "json_error"


@pytest.mark.asyncio
async def test_json_request_http_errors(monkeypatch):
    import httpx
    from app import http_utils

    class Client:
        def __init__(self, status):
            self.status = status

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, **kwargs):
            # Create a Response to attach to the error
            r = httpx.Response(self.status, request=httpx.Request(method, url))
            raise httpx.HTTPStatusError("boom", request=r.request, response=r)

    async def no_sleep(_):
        return None

    # Avoid waiting during retries
    monkeypatch.setattr(asyncio, "sleep", no_sleep)

    # 401/403 -> auth_error
    monkeypatch.setattr(http_utils.httpx, "AsyncClient", lambda: Client(401))
    data, err = await http_utils.json_request("GET", "https://x/y")
    assert data is None and err == "auth_error"

    monkeypatch.setattr(http_utils.httpx, "AsyncClient", lambda: Client(403))
    data, err = await http_utils.json_request("GET", "https://x/y")
    assert data is None and err == "auth_error"

    # 404 -> not_found
    monkeypatch.setattr(http_utils.httpx, "AsyncClient", lambda: Client(404))
    data, err = await http_utils.json_request("GET", "https://x/y")
    assert data is None and err == "not_found"


@pytest.mark.asyncio
async def test_json_request_500_retries_then_success(monkeypatch):
    import httpx
    from app import http_utils

    calls = {"n": 0}

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
            calls["n"] += 1
            if calls["n"] < 3:
                r = httpx.Response(500, request=httpx.Request(method, url))
                raise httpx.HTTPStatusError("err", request=r.request, response=r)
            return Resp()

    async def no_sleep(_):
        return None

    monkeypatch.setattr(asyncio, "sleep", no_sleep)
    monkeypatch.setattr(http_utils.httpx, "AsyncClient", lambda: Client())

    data, err = await http_utils.json_request("GET", "https://x/y")
    assert data == {"ok": True}
    assert err is None
    assert calls["n"] == 3


@pytest.mark.asyncio
async def test_json_request_network_error(monkeypatch):
    import httpx
    from app import http_utils

    calls = {"n": 0}

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, **kwargs):
            calls["n"] += 1
            req = httpx.Request(method, url)
            raise httpx.RequestError("net", request=req)

    async def no_sleep(_):
        return None

    monkeypatch.setattr(asyncio, "sleep", no_sleep)
    monkeypatch.setattr(http_utils.httpx, "AsyncClient", lambda: Client())

    data, err = await http_utils.json_request("GET", "https://x/y")
    assert data is None and err == "network_error"
    assert calls["n"] == 3


@pytest.mark.asyncio
async def test_json_request_unknown_error(monkeypatch):
    from app import http_utils

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, **kwargs):
            raise RuntimeError("boom")

    monkeypatch.setattr(http_utils.httpx, "AsyncClient", lambda: Client())

    data, err = await http_utils.json_request("GET", "https://x/y")
    assert data is None and err == "unknown_error"


