import asyncio
import json
import pytest
import httpx

from app import llama_integration
from app.http_utils import json_request


@pytest.mark.asyncio
async def test_probe_healthy_when_generate_200(monkeypatch):
    monkeypatch.setenv("OLLAMA_URL", "http://x")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")
    llama_integration.OLLAMA_URL = "http://x"
    llama_integration.OLLAMA_MODEL = "llama3"

    class Resp:
        def __init__(self):
            self.status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"response": "pong"}

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            pass

        async def request(self, method, url, **kwargs):
            return Resp()

    monkeypatch.setattr(
        llama_integration,
        "httpx",
        type("x", (), {"AsyncClient": lambda *a, **k: Client()}),
    )

    llama_integration.LLAMA_HEALTHY = False
    await llama_integration._check_and_set_flag()
    assert llama_integration.LLAMA_HEALTHY is True


@pytest.mark.asyncio
async def test_retry_fires_three_attempts(monkeypatch):
    monkeypatch.setenv("OLLAMA_URL", "http://x")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")
    llama_integration.OLLAMA_URL = "http://x"
    llama_integration.OLLAMA_MODEL = "llama3"

    attempts = {"count": 0}

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            pass

        async def request(self, method, url, **kwargs):
            attempts["count"] += 1
            if attempts["count"] < 3:
                response = httpx.Response(500, request=httpx.Request(method, url))
                raise httpx.HTTPStatusError(
                    "boom", request=response.request, response=response
                )
            return httpx.Response(
                200, request=httpx.Request(method, url), json={"ok": True}
            )

    monkeypatch.setattr(
        llama_integration,
        "httpx",
        type("x", (), {"AsyncClient": lambda *a, **k: Client()}),
    )

    async def fast_sleep(delay):
        pass

    monkeypatch.setattr(asyncio, "sleep", fast_sleep)

    data, err = await json_request("GET", "http://example.com")
    assert data == {"ok": True}
    assert attempts["count"] == 3


@pytest.mark.asyncio
async def test_token_count_matches_mocked_len(monkeypatch):
    monkeypatch.setenv("OLLAMA_URL", "http://x")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")
    llama_integration.OLLAMA_URL = "http://x"
    llama_integration.OLLAMA_MODEL = "llama3"

    tokens = [("hi", 2), ("there", 5)]
    lines = [json.dumps({"response": t, "token_len": length}) for t, length in tokens]
    lines.append(json.dumps({"done": True}))

    class Stream:
        def __init__(self):
            self.status_code = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            pass

        def raise_for_status(self):
            pass

        async def aiter_lines(self):
            for line in lines:
                yield line

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            pass

        def stream(self, method, url, json=None):
            return Stream()

    monkeypatch.setattr(
        llama_integration,
        "httpx",
        type("x", (), {"AsyncClient": lambda *a, **k: Client()}),
    )

    out = []
    async for tok in llama_integration.ask_llama("prompt"):
        out.append(tok)

    assert out == [t for t, _ in tokens]
    for tok, (_, length) in zip(out, tokens):
        assert len(tok) == length


@pytest.mark.asyncio
async def test_circuit_breaker_opens_then_closes(monkeypatch):
    monkeypatch.setenv("OLLAMA_URL", "http://x")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")
    llama_integration.OLLAMA_URL = "http://x"
    llama_integration.OLLAMA_MODEL = "llama3"

    class FailStream:
        async def __aenter__(self):
            raise httpx.RequestError("fail", request=httpx.Request("POST", "http://x"))

        async def __aexit__(self, exc_type, exc, tb):
            pass

    class FailClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            pass

        def stream(self, *a, **k):
            return FailStream()

    monkeypatch.setattr(
        llama_integration,
        "httpx",
        type("x", (), {"AsyncClient": lambda *a, **k: FailClient()}),
    )

    for _ in range(3):
        with pytest.raises(httpx.RequestError):
            async for _ in llama_integration.ask_llama("bad"):
                pass
    assert llama_integration.LLAMA_HEALTHY is False

    class OkStream:
        def __init__(self):
            self.status_code = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            pass

        def raise_for_status(self):
            pass

        async def aiter_lines(self):
            yield json.dumps({"response": "ok", "done": True})

    class OkClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            pass

        def stream(self, *a, **k):
            return OkStream()

        async def request(self, method, url, **kwargs):
            return httpx.Response(
                200, request=httpx.Request(method, url), json={"response": "pong"}
            )

    monkeypatch.setattr(
        llama_integration,
        "httpx",
        type("x", (), {"AsyncClient": lambda *a, **k: OkClient()}),
    )

    await llama_integration._check_and_set_flag()
    assert llama_integration.LLAMA_HEALTHY is True
