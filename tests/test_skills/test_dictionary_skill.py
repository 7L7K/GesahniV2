import os, sys, asyncio
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import httpx
from app.skills.dictionary_skill import DictionarySkill


DATA = [
    {
        "meanings": [
            {
                "definitions": [{"definition": "A fortunate discovery."}],
                "synonyms": ["fluke", "chance"],
            }
        ]
    }
]


class FakeClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        pass

    async def get(self, url):
        class R:
            status_code = 200
            def json(self_inner):
                return DATA
            def raise_for_status(self_inner):
                pass
        return R()


def test_dictionary(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: FakeClient())
    skill = DictionarySkill()
    m = skill.match("define serendipity")
    out = asyncio.run(skill.run("define serendipity", m))
    assert "serendipity" in out
    assert "A fortunate discovery" in out
    assert "fluke" in out
