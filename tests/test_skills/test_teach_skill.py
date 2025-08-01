import os, sys, asyncio
import pytest
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

os.environ.setdefault("OLLAMA_URL", "http://x")
os.environ.setdefault("OLLAMA_MODEL", "llama3")
os.environ.setdefault("HOME_ASSISTANT_URL", "http://ha")
os.environ.setdefault("HOME_ASSISTANT_TOKEN", "token")

from app.skills.teach_skill import TeachSkill
from app import home_assistant


def test_teach_skill_missing_entity(monkeypatch):
    skill = TeachSkill()
    m = skill.match("my office is lamp")

    async def fake_resolve(name):
        return []

    monkeypatch.setattr(home_assistant, "resolve_entity", fake_resolve)
    with pytest.raises(ValueError):
        asyncio.run(skill.run("my office is lamp", m))
