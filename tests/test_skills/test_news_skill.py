import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import httpx

from app.skills.news_skill import NewsSkill

RSS_SAMPLE = """<rss><channel><item><title>A</title></item><item><title>B</title></item><item><title>C</title></item></channel></rss>"""


class FakeClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        pass

    async def get(self, url):
        class R:
            text = RSS_SAMPLE

            def raise_for_status(self_inner):
                pass

        return R()


def test_news(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: FakeClient())
    skill = NewsSkill()
    m = skill.match("top headlines")
    out = asyncio.run(skill.run("top headlines", m))
    assert "1. A" in out
    assert "2. B" in out
    assert "3. C" in out
