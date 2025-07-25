import os, sys, asyncio
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
os.environ.setdefault("OLLAMA_URL", "http://x")
os.environ.setdefault("OLLAMA_MODEL", "llama3")
os.environ.setdefault("HOME_ASSISTANT_URL", "http://ha")
os.environ.setdefault("HOME_ASSISTANT_TOKEN", "token")

from app.skills.scene_skill import SceneSkill
from app import home_assistant


def test_scene_skill(monkeypatch):
    async def fake_resolve(name):
        return ["scene.night"]
    async def fake_call_service(domain, service, data):
        assert domain == "scene" and service == "turn_on"
    monkeypatch.setattr(home_assistant, "resolve_entity", fake_resolve)
    monkeypatch.setattr(home_assistant, "call_service", fake_call_service)
    skill = SceneSkill()
    m = skill.match("activate night scene")
    resp = asyncio.run(skill.run("activate night scene", m))
    assert "night" in resp.lower()
