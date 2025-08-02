import os, sys, asyncio
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
os.environ.setdefault("OLLAMA_URL","http://x")
os.environ.setdefault("OLLAMA_MODEL","llama3")
os.environ.setdefault("HOME_ASSISTANT_URL","http://ha")
os.environ.setdefault("HOME_ASSISTANT_TOKEN","token")

import httpx
from app.skills.currency_skill import CurrencySkill


class FakeClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        pass

    async def get(self, url, params=None):
        class R:
            def json(self_non):
                return {"result": 90}
            def raise_for_status(self_non):
                pass
        return R()


def test_currency_skill(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: FakeClient())
    skill = CurrencySkill()
    m = skill.match("100 usd to eur")
    assert m
    resp = asyncio.run(skill.run("100 usd to eur", m))
    assert "90.00 EUR" in resp
