import os, sys, asyncio
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
os.environ.setdefault("OLLAMA_URL", "http://x")
os.environ.setdefault("OLLAMA_MODEL", "llama3")
os.environ.setdefault("HOME_ASSISTANT_URL", "http://ha")
os.environ.setdefault("HOME_ASSISTANT_TOKEN", "token")

from app.skills.notify_skill import NotifySkill
from app import home_assistant


def test_notify_skill(monkeypatch):
    async def fake_call_service(domain, service, data):
        assert domain == "notify" and service == "mobile_app_phone"
        assert data["message"] == "Hello"
    monkeypatch.setattr(home_assistant, "call_service", fake_call_service)
    skill = NotifySkill()
    m = skill.match("notify Hello")
    resp = asyncio.run(skill.run("notify Hello", m))
    assert "Notification" in resp
