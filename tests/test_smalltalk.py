import os
import sys
import asyncio
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("HOME_ASSISTANT_URL", "http://ha")
os.environ.setdefault("HOME_ASSISTANT_TOKEN", "token")
os.environ.setdefault("OLLAMA_URL", "http://x")
os.environ.setdefault("OLLAMA_MODEL", "llama3")
os.environ.setdefault("SMALLTALK_PERSONA_RATE", "0")

from app.skills.smalltalk_skill import GREETINGS, SmalltalkSkill, is_greeting
from app import router, skills  # noqa: F401


def test_is_greeting():
    assert is_greeting("hi")
    assert is_greeting("yo!")
    assert is_greeting("HELLO?")
    assert not is_greeting("what's new")


def test_handle_returns_valid_format():
    s = SmalltalkSkill()

    class User:
        last_project = "garage build"

    resp = asyncio.run(s.handle("hello", User()))
    assert resp is not None
    assert any(resp.startswith(g) for g in GREETINGS)
    assert resp.endswith("?")


def test_router_integration():
    result = asyncio.run(router.route_prompt("hello", user_id="u"))
    assert any(result.startswith(g) for g in GREETINGS)


def test_cached_responses_are_deterministic():
    s = SmalltalkSkill(persona_rate=0)
    first = asyncio.run(s.handle("hi"))
    second = asyncio.run(s.handle("hi"))
    assert first == second


def test_router_uses_smalltalk_cache():
    first = asyncio.run(router.route_prompt("yo", user_id="u"))
    second = asyncio.run(router.route_prompt("yo", user_id="u"))
    assert first == second


def test_time_provider_injection():
    morning = SmalltalkSkill(
        time_provider=lambda: datetime(2024, 1, 1, 8), persona_rate=0
    )
    resp = asyncio.run(morning.handle("hi"))
    assert "Ready to crush the day?" in resp


def test_memory_hook_formatting():
    s = SmalltalkSkill(persona_rate=0)

    class User:
        last_project = "garage build"

    resp = asyncio.run(s.handle("hello", User()))
    assert "`Garage build`" in resp
