import asyncio
import os
import sys

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


def test_synonyms_of_variant(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: FakeClient())
    skill = DictionarySkill()
    m = skill.match("synonyms of serendipity")
    out = asyncio.run(skill.run("synonyms of serendipity", m))
    assert "Synonyms" in out


def test_what_does_mean_variant(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: FakeClient())
    skill = DictionarySkill()
    m = skill.match("what does serendipity mean")
    out = asyncio.run(skill.run("what does serendipity mean", m))
    assert "serendipity:" in out.lower()


def test_dictionary_no_meanings(monkeypatch):
    class EmptyClient:
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc, tb):
            pass
        async def get(self, url):
            class R:
                status_code = 200
                def json(self_inner):
                    return [{}]
                def raise_for_status(self_inner):
                    pass
            return R()

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: EmptyClient())
    skill = DictionarySkill()
    m = skill.match("define foo")
    out = asyncio.run(skill.run("define foo", m))
    assert "No definition found" in out


def test_dictionary_service_unreachable(monkeypatch):
    class BadClient:
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc, tb):
            pass
        async def get(self, url):
            raise RuntimeError("boom")

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: BadClient())
    skill = DictionarySkill()
    m = skill.match("define test")
    out = asyncio.run(skill.run("define test", m))
    assert "unreachable" in out.lower()
