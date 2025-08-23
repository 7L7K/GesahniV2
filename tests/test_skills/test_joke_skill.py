import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import httpx

from app.skills.joke_skill import JokeSkill


class FakeClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        pass

    async def get(self, url):
        class R:
            def json(self_inner):
                return {"setup": "Why?", "punchline": "Because."}

            def raise_for_status(self_inner):
                pass

        return R()


def test_joke(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: FakeClient())
    skill = JokeSkill()
    m = skill.match("tell me a joke")
    out = asyncio.run(skill.run("tell me a joke", m))
    assert out == "Why? Because."
