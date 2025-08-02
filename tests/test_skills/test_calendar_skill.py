import os, sys, asyncio
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
os.environ.setdefault("OLLAMA_URL", "http://x")
os.environ.setdefault("OLLAMA_MODEL", "llama3")
os.environ.setdefault("HOME_ASSISTANT_URL", "http://ha")
os.environ.setdefault("HOME_ASSISTANT_TOKEN", "token")

from app.skills.calendar_skill import CalendarSkill
from app import home_assistant


def test_calendar_skill(monkeypatch):
    async def fake_request(method, path, json=None, timeout=10.0):
        return [
            {"summary": "Meeting", "start": {"dateTime": "2024-07-10T09:00:00-04:00"}},
            {"summary": "Lunch", "start": {"dateTime": "2024-07-10T12:00:00-04:00"}},
        ]
    monkeypatch.setattr(home_assistant, "_request", fake_request)
    skill = CalendarSkill()
    m = skill.match("what's on my calendar today")
    resp = asyncio.run(skill.run("what's on my calendar today", m))
    assert "Meeting" in resp and "Lunch" in resp
