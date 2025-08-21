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


@pytest.mark.asyncio
async def test_json_request_import_fallback(monkeypatch):
    """Test the fallback when llama_integration import fails."""
    from app import http_utils

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
            return Resp()

    # Mock importlib to raise an exception
    def mock_import_module(module_name):
        if module_name == "app.llama_integration":
            raise ImportError("Module not found")
        return None

    monkeypatch.setattr(http_utils.importlib, "import_module", mock_import_module)
    monkeypatch.setattr(http_utils.httpx, "AsyncClient", lambda: Client())

    data, err = await http_utils.json_request("GET", "https://x/y")
    assert data == {"ok": True}
    assert err is None


@pytest.mark.asyncio
async def test_json_request_timeout_default(monkeypatch):
    """Test that timeout defaults to 10.0 when not provided."""
    from app import http_utils

    class Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"ok": True}

    class Client:
        def __init__(self, timeout=None):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, **kwargs):
            return Resp()

    # Mock AsyncClient to capture the timeout parameter
    captured_timeout = None
    def mock_async_client(timeout=None):
        nonlocal captured_timeout
        captured_timeout = timeout
        return Client(timeout)

    monkeypatch.setattr(http_utils.httpx, "AsyncClient", mock_async_client)

    data, err = await http_utils.json_request("GET", "https://x/y")
    assert data == {"ok": True}
    assert err is None
    assert captured_timeout == 10.0


@pytest.mark.asyncio
async def test_json_request_custom_timeout(monkeypatch):
    """Test that custom timeout is passed through."""
    from app import http_utils

    class Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"ok": True}

    class Client:
        def __init__(self, timeout=None):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, **kwargs):
            return Resp()

    captured_timeout = None
    def mock_async_client(timeout=None):
        nonlocal captured_timeout
        captured_timeout = timeout
        return Client(timeout)

    monkeypatch.setattr(http_utils.httpx, "AsyncClient", mock_async_client)

    data, err = await http_utils.json_request("GET", "https://x/y", timeout=30.0)
    assert data == {"ok": True}
    assert err is None
    assert captured_timeout == 30.0


@pytest.mark.asyncio
async def test_json_request_asyncclient_typeerror_fallback(monkeypatch):
    """Test fallback when AsyncClient doesn't accept timeout parameter."""
    from app import http_utils

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
            return Resp()

    # Mock AsyncClient to raise TypeError on first call, then succeed
    call_count = 0
    def mock_async_client(timeout=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise TypeError("AsyncClient() takes no arguments")
        return Client()

    monkeypatch.setattr(http_utils.httpx, "AsyncClient", mock_async_client)

    data, err = await http_utils.json_request("GET", "https://x/y")
    assert data == {"ok": True}
    assert err is None
    assert call_count == 2


@pytest.mark.asyncio
async def test_json_request_all_retries_exhausted(monkeypatch):
    """Test that all retries are exhausted and final error is returned."""
    import httpx
    from app import http_utils

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, **kwargs):
            # Always return 500 error to trigger retries
            r = httpx.Response(500, request=httpx.Request(method, url))
            raise httpx.HTTPStatusError("err", request=r.request, response=r)

    async def no_sleep(_):
        return None

    monkeypatch.setattr(asyncio, "sleep", no_sleep)
    monkeypatch.setattr(http_utils.httpx, "AsyncClient", lambda: Client())

    data, err = await http_utils.json_request("GET", "https://x/y")
    assert data is None
    assert err == "http_error"


@pytest.mark.asyncio
async def test_json_request_network_error_all_retries_exhausted(monkeypatch):
    """Test that network errors exhaust all retries and return network_error."""
    import httpx
    from app import http_utils

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, **kwargs):
            # Always raise network error to trigger retries
            req = httpx.Request(method, url)
            raise httpx.RequestError("net", request=req)

    async def no_sleep(_):
        return None

    monkeypatch.setattr(asyncio, "sleep", no_sleep)
    monkeypatch.setattr(http_utils.httpx, "AsyncClient", lambda: Client())

    data, err = await http_utils.json_request("GET", "https://x/y")
    assert data is None
    assert err == "network_error"


@pytest.mark.asyncio
async def test_json_request_non_retryable_http_error_all_attempts(monkeypatch):
    """Test that non-retryable HTTP errors (like 400) exhaust all attempts and return http_error."""
    import httpx
    from app import http_utils

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, **kwargs):
            # Always return 400 error (not retryable, not 401/403/404)
            r = httpx.Response(400, request=httpx.Request(method, url))
            raise httpx.HTTPStatusError("err", request=r.request, response=r)

    async def no_sleep(_):
        return None

    monkeypatch.setattr(asyncio, "sleep", no_sleep)
    monkeypatch.setattr(http_utils.httpx, "AsyncClient", lambda: Client())

    data, err = await http_utils.json_request("GET", "https://x/y")
    assert data is None
    assert err == "http_error"


@pytest.mark.asyncio
async def test_json_request_final_return_statement(monkeypatch):
    """Test the final return statement when all retries are exhausted."""
    import httpx
    from app import http_utils

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, **kwargs):
            # Return a 400 error which is not retryable and not in the special status codes
            r = httpx.Response(400, request=httpx.Request(method, url))
            raise httpx.HTTPStatusError("err", request=r.request, response=r)

    monkeypatch.setattr(http_utils.httpx, "AsyncClient", lambda: Client())

    data, err = await http_utils.json_request("GET", "https://x/y")
    assert data is None
    assert err == "http_error"


@pytest.mark.asyncio
async def test_json_request_custom_exception_type(monkeypatch):
    """Test with a custom exception type that should trigger the final return."""
    from app import http_utils

    class CustomException(Exception):
        pass

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, **kwargs):
            raise CustomException("custom error")

    monkeypatch.setattr(http_utils.httpx, "AsyncClient", lambda: Client())

    data, err = await http_utils.json_request("GET", "https://x/y")
    assert data is None
    assert err == "unknown_error"


@pytest.mark.asyncio
async def test_json_request_context_manager_exception(monkeypatch):
    """Test when the context manager raises an exception during exit."""
    from app import http_utils

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            # Raise an exception during context exit
            raise RuntimeError("context exit error")

        async def request(self, method, url, **kwargs):
            # Return a successful response
            class Resp:
                def raise_for_status(self):
                    return None

                def json(self):
                    return {"ok": True}
            return Resp()

    monkeypatch.setattr(http_utils.httpx, "AsyncClient", lambda: Client())

    data, err = await http_utils.json_request("GET", "https://x/y")
    assert data is None
    assert err == "unknown_error"


