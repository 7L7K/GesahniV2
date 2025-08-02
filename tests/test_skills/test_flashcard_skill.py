import os, sys, asyncio, random
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
os.environ.setdefault("OLLAMA_URL", "http://x")
os.environ.setdefault("OLLAMA_MODEL", "llama3")
os.environ.setdefault("HOME_ASSISTANT_URL", "http://ha")
os.environ.setdefault("HOME_ASSISTANT_TOKEN", "token")

from app.skills.flashcard_skill import FlashcardSkill


def test_flashcard_skill(monkeypatch):
    monkeypatch.setattr(random, "choice", lambda deck: ("cat", "gato"))
    monkeypatch.setattr(random, "random", lambda: 0.1)
    skill = FlashcardSkill()
    m = skill.match("flashcard")
    resp = asyncio.run(skill.run("flashcard", m))
    assert "cat" in resp
    assert "Spanish" in resp
