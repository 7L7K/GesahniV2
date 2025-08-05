import os, sys, asyncio

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
os.environ.setdefault("OLLAMA_URL", "http://x")
os.environ.setdefault("OLLAMA_MODEL", "llama3")
os.environ.setdefault("HOME_ASSISTANT_URL", "http://ha")
os.environ.setdefault("HOME_ASSISTANT_TOKEN", "token")
os.environ.setdefault("OPENWEATHER_API_KEY", "dummy")

import httpx
from app.skills.forecast_skill import ForecastSkill


class FakeClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        pass

    async def get(self, url, params=None):
        class R:
            def json(self_non):
                return {
                    "list": [
                        {"dt_txt": "2025-01-01 00:00:00", "main": {"temp": 50}},
                        {"dt_txt": "2025-01-01 03:00:00", "main": {"temp": 60}},
                        {"dt_txt": "2025-01-02 00:00:00", "main": {"temp": 55}},
                        {"dt_txt": "2025-01-02 03:00:00", "main": {"temp": 65}},
                        {"dt_txt": "2025-01-03 00:00:00", "main": {"temp": 70}},
                        {"dt_txt": "2025-01-03 03:00:00", "main": {"temp": 80}},
                    ]
                }

            def raise_for_status(self_non):
                pass

        return R()


def test_forecast_skill(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: FakeClient())
    import app.skills.forecast_skill as fs

    monkeypatch.setattr(fs, "OPENWEATHER_KEY", "dummy")
    skill = ForecastSkill()
    m = skill.match("3 day forecast for Paris")
    assert m
    resp = asyncio.run(skill.run("3 day forecast for Paris", m))
    assert "Wed" in resp and resp.count("|") == 2
