import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
os.environ.setdefault("OLLAMA_URL", "http://x")
os.environ.setdefault("OLLAMA_MODEL", "llama3")
os.environ.setdefault("HOME_ASSISTANT_URL", "http://ha")
os.environ.setdefault("HOME_ASSISTANT_TOKEN", "token")
os.environ.setdefault("ALPHAVANTAGE_API_KEY", "demo")

import httpx
from app.skills.stock_price_skill import StockPriceSkill


class FakeClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        pass

    async def get(self, url, params=None):
        class R:
            def json(self_non):
                return {"Global Quote": {"05. price": "123.45"}}

            def raise_for_status(self_non):
                pass

        return R()


def test_stock_price_skill(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: FakeClient())
    import app.skills.stock_price_skill as sp

    monkeypatch.setattr(sp, "ALPHAVANTAGE_KEY", "demo")
    skill = StockPriceSkill()
    m = skill.match("stock price of aapl")
    assert m
    resp = asyncio.run(skill.run("stock price of aapl", m))
    assert "AAPL is $123.45" in resp


def test_stock_quote(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: FakeClient())
    import app.skills.stock_price_skill as sp

    monkeypatch.setattr(sp, "ALPHAVANTAGE_KEY", "demo")
    skill = StockPriceSkill()
    m = skill.match("AAPL quote")
    assert m
    resp = asyncio.run(skill.run("AAPL quote", m))
    assert "AAPL is $123.45" in resp
