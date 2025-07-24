import os, sys, asyncio, re
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

os.environ.setdefault("HOME_ASSISTANT_URL", "http://ha")
os.environ.setdefault("HOME_ASSISTANT_TOKEN", "token")
os.environ.setdefault("OLLAMA_URL", "http://x")
os.environ.setdefault("OLLAMA_MODEL", "llama3")
import app.skills.base as base

class Dummy(base.Skill):
    PATTERNS = [re.compile(r"hello", re.I)]

    async def run(self, prompt, match):
        return "world"

def test_check_builtin_skills_match():
    dummy = Dummy()
    base.SKILLS.insert(0, dummy)
    resp = asyncio.run(base.check_builtin_skills("hello there"))
    base.SKILLS.pop(0)
    assert resp == "world"

def test_check_builtin_skills_none():
    resp = asyncio.run(base.check_builtin_skills("no match"))
    assert resp is None
