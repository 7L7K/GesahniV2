import asyncio

from app import llama_integration


class FakeCounter:
    def __init__(self):
        self.counts = {}

    def labels(self, **labels):
        direction = labels.get("direction")
        self.counts.setdefault(direction, 0)
        parent = self

        class Child:
            def inc(self, amount=1.0):
                parent.counts[direction] += amount

        return Child()


class FakeHistogram:
    def __init__(self):
        self.values = []

    def labels(self, **labels):
        return self

    def observe(self, amount):
        self.values.append(amount)


class FakeStream:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        pass

    def raise_for_status(self):
        pass

    async def aiter_lines(self):
        yield '{"response":"hi"}'
        yield '{"response":" there", "done": true}'


class FakeClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        pass

    def stream(self, method, url, json):
        return FakeStream()


def test_llama_metrics(monkeypatch):
    monkeypatch.setenv("OLLAMA_URL", "http://x")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")
    llama_integration.OLLAMA_URL = "http://x"
    llama_integration.OLLAMA_MODEL = "llama3"

    tokens = FakeCounter()
    latency = FakeHistogram()
    monkeypatch.setattr(llama_integration, "LLAMA_TOKENS", tokens)
    monkeypatch.setattr(llama_integration, "LLAMA_LATENCY", latency)
    monkeypatch.setattr(
        llama_integration,
        "httpx",
        type("x", (), {"AsyncClient": lambda *a, **k: FakeClient()}),
    )

    async def run():
        out = []
        async for tok in llama_integration.ask_llama("hello world"):
            out.append(tok)
        return out

    result = asyncio.run(run())
    assert "".join(result) == "hi there"
    assert tokens.counts["prompt"] == 2
    assert tokens.counts["completion"] == 2
    assert len(latency.values) == 1
    assert latency.values[0] >= 0
