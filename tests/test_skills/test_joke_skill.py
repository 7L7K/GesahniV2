import os, sys, asyncio
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
os.environ.setdefault("OLLAMA_URL","http://x")
os.environ.setdefault("OLLAMA_MODEL","llama3")
os.environ.setdefault("HOME_ASSISTANT_URL","http://ha")
os.environ.setdefault("HOME_ASSISTANT_TOKEN","token")

import httpx
from app.skills.joke_skill import JokeSkill


class FakeClient:
    async def __aenter__(self):
        return self
    async def __aexit__(self, exc_type, exc, tb):
        pass
    async def get(self, url):
        class R:
            def json(self):
                return {"setup": "a", "punchline": "b"}
            def raise_for_status(self):
                pass
        return R()

def test_joke_skill(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", lambda timeout=5: FakeClient())
    skill = JokeSkill()
    m = skill.match("tell me a joke")
    assert m
    resp = asyncio.run(skill.run("tell me a joke", m))
    assert "a" in resp
