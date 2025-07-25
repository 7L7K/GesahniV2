import os, sys, asyncio
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
os.environ.setdefault("OLLAMA_URL", "http://x")
os.environ.setdefault("OLLAMA_MODEL", "llama3")
os.environ.setdefault("HOME_ASSISTANT_URL", "http://ha")
os.environ.setdefault("HOME_ASSISTANT_TOKEN", "token")

from app.skills.timer_skill import TimerSkill
from app import home_assistant


def test_timer_skill(monkeypatch):
    called = {}
    async def fake_call_service(domain, service, data):
        called.update({"domain": domain, "service": service, "data": data})
    monkeypatch.setattr(home_assistant, "call_service", fake_call_service)
    skill = TimerSkill()
    m = skill.match("start a timer for 2 minutes")
    resp = asyncio.run(skill.run("start a timer for 2 minutes", m))
    assert called["domain"] == "timer"
    assert called["service"] == "start"
    assert "2 minutes" in resp
