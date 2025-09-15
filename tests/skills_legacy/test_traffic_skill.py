import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
os.environ.setdefault("OLLAMA_URL", "http://x")
os.environ.setdefault("OLLAMA_MODEL", "llama3")
os.environ.setdefault("HOME_ASSISTANT_URL", "http://ha")
os.environ.setdefault("HOME_ASSISTANT_TOKEN", "token")
os.environ.setdefault("CITY_NAME", "Detroit,US")

import httpx

from app.skills.traffic_skill import TrafficSkill


class BaseClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        pass


class AnnArborClient(BaseClient):
    async def get(self, url, params=None, headers=None):
        class R:
            def __init__(self, data):
                self._data = data

            def json(self):
                return self._data

            def raise_for_status(self):
                pass

        if "nominatim" in url:
            q = params["q"]
            if q == "Detroit,US":
                return R([{"lat": "42.3314", "lon": "-83.0458"}])
            return R([{"lat": "42.2808", "lon": "-83.7430"}])
        return R({"routes": [{"duration": 3600}]})


class ChicagoClient(BaseClient):
    async def get(self, url, params=None, headers=None):
        class R:
            def __init__(self, data):
                self._data = data

            def json(self):
                return self._data

            def raise_for_status(self):
                pass

        if "nominatim" in url:
            q = params["q"]
            if q == "Detroit,US":
                return R([{"lat": "42.3314", "lon": "-83.0458"}])
            return R([{"lat": "41.8781", "lon": "-87.6298"}])
        return R({"routes": [{"duration": 7200}]})


def test_traffic_ann_arbor(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", lambda timeout=10: AnnArborClient())
    skill = TrafficSkill()
    m = skill.match("traffic to ann arbor")
    resp = asyncio.run(skill.run("traffic to ann arbor", m))
    assert "Ann Arbor" in resp
    assert "60 minutes" in resp


def test_drive_to_chicago(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", lambda timeout=10: ChicagoClient())
    skill = TrafficSkill()
    m = skill.match("how long to drive to Chicago")
    resp = asyncio.run(skill.run("how long to drive to Chicago", m))
    assert "Chicago" in resp
    assert "120 minutes" in resp
