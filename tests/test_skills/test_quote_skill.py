import os, sys, asyncio
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
os.environ.setdefault("OLLAMA_URL","http://x")
os.environ.setdefault("OLLAMA_MODEL","llama3")
os.environ.setdefault("HOME_ASSISTANT_URL","http://ha")
os.environ.setdefault("HOME_ASSISTANT_TOKEN","token")

from app.skills.quote_skill import QuoteSkill


def test_quote_skill():
    skill = QuoteSkill()
    m = skill.match("give me a motivational quote")
    assert m
    resp = asyncio.run(skill.run("give me a motivational quote", m))
    assert isinstance(resp, str) and len(resp) > 0
