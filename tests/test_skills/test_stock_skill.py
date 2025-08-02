import os, sys, asyncio
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
os.environ.setdefault("OLLAMA_URL","http://x")
os.environ.setdefault("OLLAMA_MODEL","llama3")
os.environ.setdefault("HOME_ASSISTANT_URL","http://ha")
os.environ.setdefault("HOME_ASSISTANT_TOKEN","token")

import httpx
from app.skills.stock_skill import StockSkill


class FakeClient:
    async def __aenter__(self):
        return self
    async def __aexit__(self, exc_type, exc, tb):
        pass
    async def get(self, url, params=None):
        class R:
            def json(self):
                return {"quoteResponse": {"result": [{"regularMarketPrice": 123.45}]}}
            def raise_for_status(self):
                pass
        return R()

def test_stock_skill(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", lambda timeout=5: FakeClient())
    skill = StockSkill()
    m = skill.match("what's AAPL at?")
    assert m
    resp = asyncio.run(skill.run("what's AAPL at?", m))
    assert "AAPL" in resp
