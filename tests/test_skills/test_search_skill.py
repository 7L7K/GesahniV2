import os, sys, asyncio
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import httpx
from app.skills.search_skill import SearchSkill


class FakeClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        pass

    async def get(self, url, params=None):
        class R:
            def json(self_inner):
                return {"Answer": "Paris"}
            def raise_for_status(self_inner):
                pass
        return R()


def test_search(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: FakeClient())
    skill = SearchSkill()
    m = skill.match("who is napoleon")
    out = asyncio.run(skill.run("who is napoleon", m))
    assert out == "Paris"
