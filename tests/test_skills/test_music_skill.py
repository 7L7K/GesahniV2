import os, sys, asyncio
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
os.environ.setdefault("OLLAMA_URL","http://x")
os.environ.setdefault("OLLAMA_MODEL","llama3")
os.environ.setdefault("HOME_ASSISTANT_URL","http://ha")
os.environ.setdefault("HOME_ASSISTANT_TOKEN","token")

from app.skills.music_skill import MusicSkill
from app import home_assistant


def test_music_play(monkeypatch):
    async def fake_call_service(domain, service, data):
        assert service == "media_play"
    monkeypatch.setattr(home_assistant, "call_service", fake_call_service)
    skill = MusicSkill()
    m = skill.match("play music")
    resp = asyncio.run(skill.run("play music", m))
    assert "Music playe" in resp or "Music play" in resp


def test_music_artist(monkeypatch):
    async def fake_call_service(domain, service, data):
        assert service == "play_media"
        assert data["media_content_id"] == "spotify:artist:NERD"
    monkeypatch.setattr(home_assistant, "call_service", fake_call_service)
    skill = MusicSkill()
    m = skill.match("play N.E.R.D")
    resp = asyncio.run(skill.run("play N.E.R.D", m))
    assert "Playing" in resp
