import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
os.environ.setdefault("OLLAMA_URL", "http://x")
os.environ.setdefault("OLLAMA_MODEL", "llama3")
os.environ.setdefault("HOME_ASSISTANT_URL", "http://ha")
os.environ.setdefault("HOME_ASSISTANT_TOKEN", "token")

from app.skills.clock_skill import ClockSkill


def test_clock_skill_match_and_run(monkeypatch):
    skill = ClockSkill()
    m = skill.match("countdown 5")
    assert m
    resp = asyncio.run(skill.run("countdown 5", m))
    assert resp == "Countdown of 5 seconds started."
