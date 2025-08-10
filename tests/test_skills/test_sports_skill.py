import asyncio
import os
import sys
import importlib.util
import types
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import httpx

repo_root = Path(__file__).resolve().parents[2]
app_pkg = types.ModuleType("app")
app_pkg.__path__ = [str(repo_root / "app")]
sys.modules["app"] = app_pkg
skills_pkg = types.ModuleType("app.skills")
skills_pkg.__path__ = [str(repo_root / "app" / "skills")]
sys.modules["app.skills"] = skills_pkg

router_stub = types.ModuleType("app.router")
router_stub.llama_circuit_open = False
router_stub.LLAMA_HEALTHY = True
sys.modules["app.router"] = router_stub
model_picker_stub = types.ModuleType("app.model_picker")
model_picker_stub.LLAMA_HEALTHY = True
sys.modules["app.model_picker"] = model_picker_stub

llama_stub = types.ModuleType("app.llama_integration")
llama_stub.LLAMA_HEALTHY = True
sys.modules["app.llama_integration"] = llama_stub

base_path = repo_root / "app" / "skills" / "base.py"
base_spec = importlib.util.spec_from_file_location("app.skills.base", base_path)
base_module = importlib.util.module_from_spec(base_spec)
base_spec.loader.exec_module(base_module)
sys.modules["app.skills.base"] = base_module

sports_path = repo_root / "app" / "skills" / "sports_skill.py"
sports_spec = importlib.util.spec_from_file_location("app.skills.sports_skill", sports_path)
sports_module = importlib.util.module_from_spec(sports_spec)
sports_spec.loader.exec_module(sports_module)
SportsSkill = sports_module.SportsSkill


class FakeResponse:
    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data

    def raise_for_status(self):
        pass


class FakeClient:
    def __init__(self, responses):
        self._responses = responses
        self._index = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        pass

    async def get(self, url, params=None):
        resp = self._responses[self._index]
        self._index += 1
        return resp


def test_did_team_win(monkeypatch):
    responses = [
        FakeResponse({"teams": [{"idTeam": "1", "strTeam": "Example FC"}]}),
        FakeResponse(
            {
                "results": [
                    {
                        "strHomeTeam": "Example FC",
                        "strAwayTeam": "Rivals FC",
                        "intHomeScore": "3",
                        "intAwayScore": "1",
                    }
                ]
            }
        ),
    ]
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: FakeClient(responses))
    skill = SportsSkill()
    m = skill.match("did the Example FC win")
    out = asyncio.run(skill.run("did the Example FC win", m))
    assert "Example FC won 3-1" in out
    assert "Rivals FC" in out


def test_next_game(monkeypatch):
    responses = [
        FakeResponse({"teams": [{"idTeam": "1", "strTeam": "Example FC"}]}),
        FakeResponse(
            {
                "events": [
                    {
                        "strHomeTeam": "Example FC",
                        "strAwayTeam": "Rivals FC",
                        "dateEvent": "2025-06-01",
                        "strTime": "19:00:00",
                    }
                ]
            }
        ),
    ]
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: FakeClient(responses))
    skill = SportsSkill()
    m = skill.match("next game for Example FC")
    out = asyncio.run(skill.run("next game for Example FC", m))
    assert "next game for the Example FC" in out
    assert "Rivals FC" in out
    assert "2025-06-01" in out
