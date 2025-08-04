import os, sys, asyncio
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
os.environ.setdefault("OLLAMA_URL","http://x")
os.environ.setdefault("OLLAMA_MODEL","llama3")
os.environ.setdefault("HOME_ASSISTANT_URL","http://ha")
os.environ.setdefault("HOME_ASSISTANT_TOKEN","token")
os.environ.setdefault("OPENWEATHER_API_KEY","dummy")

import httpx
from app.skills.weather_skill import WeatherSkill


class FakeClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        pass

    async def get(self, url, params=None):
        class R:
            def json(self_non):
                return {"main": {"temp": 20}, "weather": [{"description": "clear"}]}
            def raise_for_status(self_non):
                pass
        return R()


class FakeClientZero:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        pass

    async def get(self, url, params=None):
        class R:
            def json(self_non):
                return {"main": {"temp": 0}, "weather": [{"description": "clear"}]}

            def raise_for_status(self_non):
                pass

        return R()


def test_weather_skill(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: FakeClient())
    import app.skills.weather_skill as ws
    monkeypatch.setattr(ws, "OPENWEATHER_KEY", "dummy")
    skill = WeatherSkill()
    m = skill.match("weather in paris")
    resp = asyncio.run(skill.run("weather in paris", m))
    assert "Paris" in resp


def test_weather_skill_zero_temp(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: FakeClientZero())
    import app.skills.weather_skill as ws
    monkeypatch.setattr(ws, "OPENWEATHER_KEY", "dummy")
    skill = WeatherSkill()
    m = skill.match("weather in paris")
    resp = asyncio.run(skill.run("weather in paris", m))
    assert "0°F" in resp
