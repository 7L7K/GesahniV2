import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
os.environ.setdefault("OLLAMA_URL", "http://x")
os.environ.setdefault("OLLAMA_MODEL", "llama3")
os.environ.setdefault("HOME_ASSISTANT_URL", "http://ha")
os.environ.setdefault("HOME_ASSISTANT_TOKEN", "token")

import httpx

from app.skills.stock_skill import StockSkill


class QuoteClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        pass

    async def get(self, url, params=None):
        if "finance.yahoo.com" in url:

            class R:
                def json(self):
                    return {
                        "quoteResponse": {
                            "result": [
                                {
                                    "symbol": "AAPL",
                                    "regularMarketPrice": 123.45,
                                    "currency": "USD",
                                }
                            ]
                        }
                    }

                def raise_for_status(self):
                    pass

            return R()
        else:
            raise AssertionError("unexpected URL")


class CryptoClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        pass

    async def get(self, url, params=None):
        if "finance.yahoo.com" in url:

            class R:
                def json(self):
                    return {
                        "quoteResponse": {
                            "result": [
                                {
                                    "symbol": "BTC-USD",
                                    "regularMarketPrice": 100,
                                    "currency": "USD",
                                }
                            ]
                        }
                    }

                def raise_for_status(self):
                    pass

            return R()
        else:

            class R:
                def json(self):
                    return {"result": 90}

                def raise_for_status(self):
                    pass

            return R()


class ErrorClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        pass

    async def get(self, url, params=None):
        class R:
            def json(self):
                return {"quoteResponse": {"result": []}}

            def raise_for_status(self):
                pass

        return R()


def test_stock_price(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: QuoteClient())
    skill = StockSkill()
    m = skill.match("stock price for AAPL")
    assert m
    resp = asyncio.run(skill.run("stock price for AAPL", m))
    assert "AAPL" in resp and "123.45 USD" in resp


def test_crypto_price_conversion(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: CryptoClient())
    skill = StockSkill()
    m = skill.match("btc price in eur")
    assert m
    resp = asyncio.run(skill.run("btc price in eur", m))
    assert "BTC" in resp and "90.00 EUR" in resp


def test_stock_price_error(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: ErrorClient())
    skill = StockSkill()
    m = skill.match("stock price for XXXX")
    assert m
    resp = asyncio.run(skill.run("stock price for XXXX", m))
    assert resp == "Stock price lookup failed."
