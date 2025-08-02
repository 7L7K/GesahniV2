import os, sys, asyncio
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
os.environ.setdefault("OLLAMA_URL","http://x")
os.environ.setdefault("OLLAMA_MODEL","llama3")
os.environ.setdefault("HOME_ASSISTANT_URL","http://ha")
os.environ.setdefault("HOME_ASSISTANT_TOKEN","token")

from app.skills.world_clock_skill import WorldClockSkill


def test_world_clock_skill():
    skill = WorldClockSkill()
    m = skill.match("what time is it in Tokyo?")
    assert m
    resp = asyncio.run(skill.run("what time is it in Tokyo?", m))
    assert "Tokyo" in resp
