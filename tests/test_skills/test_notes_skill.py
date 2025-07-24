import os, sys, asyncio, tempfile
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
os.environ.setdefault("OLLAMA_URL","http://x")
os.environ.setdefault("OLLAMA_MODEL","llama3")
os.environ.setdefault("HOME_ASSISTANT_URL","http://ha")
os.environ.setdefault("HOME_ASSISTANT_TOKEN","token")

os.environ["NOTES_DB"] = tempfile.mkstemp()[1]

from importlib import reload
from app.skills import notes_skill
reload(notes_skill)
from app.skills.notes_skill import NotesSkill


def test_notes(monkeypatch):
    skill = NotesSkill()
    m1 = skill.match("note hello")
    asyncio.run(skill.run("note hello", m1))
    m2 = skill.match("show notes")
    out = asyncio.run(skill.run("show notes", m2))
    assert "hello" in out
