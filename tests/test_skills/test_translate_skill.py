import os, sys, asyncio
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import httpx
from app.skills.translate_skill import TranslateSkill


class FakeClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        pass

    async def post(self, url, json=None):
        class R:
            def json(self_inner):
                if url.endswith("/translate"):
                    return {"translatedText": "hola"}
                return [{"language": "es"}]
            def raise_for_status(self_inner):
                pass
        return R()


def test_translate(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: FakeClient())
    skill = TranslateSkill()
    m = skill.match("translate hello to es")
    out = asyncio.run(skill.run("translate hello to es", m))
    assert out == "hola"


def test_detect(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: FakeClient())
    skill = TranslateSkill()
    m = skill.match("detect language of bonjour")
    out = asyncio.run(skill.run("detect language of bonjour", m))
    assert out == "es"
