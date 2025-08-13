import os, sys, asyncio

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import httpx
from app.skills.url_title_skill import UrlTitleSkill


def test_url_title(monkeypatch):
    class Client:
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc, tb):
            pass
        async def get(self, url):
            class R:
                text = "<html><title>Hello World</title></html>"
                def raise_for_status(self):
                    pass
            return R()

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: Client())
    s = UrlTitleSkill()
    q = "what is the title of https://example.com"
    m = s.match(q)
    out = asyncio.run(s.run(q, m))
    assert out == "Hello World"


