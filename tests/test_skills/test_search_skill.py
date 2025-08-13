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


def test_search_was_are_variants(monkeypatch):
    class Client:
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc, tb):
            pass
        async def get(self, url, params=None):
            class R:
                def json(self_inner):
                    return {"AbstractText": "Answer text"}
                def raise_for_status(self_inner):
                    pass
            return R()

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: Client())
    skill = SearchSkill()
    m = skill.match("who was Ada Lovelace")
    out = asyncio.run(skill.run("who was Ada Lovelace", m))
    assert out == "Answer text"


def test_search_related_topics_fallback(monkeypatch):
    class Client:
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc, tb):
            pass
        async def get(self, url, params=None):
            class R:
                def json(self_inner):
                    return {"RelatedTopics": [{"Text": "Alt snippet"}]}
                def raise_for_status(self_inner):
                    pass
            return R()

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: Client())
    skill = SearchSkill()
    m = skill.match("what is flux capacitor")
    out = asyncio.run(skill.run("what is flux capacitor", m))
    assert out == "Alt snippet"


def test_search_service_unreachable(monkeypatch):
    class Bad:
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc, tb):
            pass
        async def get(self, url, params=None):
            raise RuntimeError("boom")

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: Bad())
    skill = SearchSkill()
    m = skill.match("search test")
    out = asyncio.run(skill.run("search test", m))
    assert "unreachable" in out.lower()
