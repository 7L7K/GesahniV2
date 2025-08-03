import os, sys
import asyncio

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
os.environ.setdefault('HOME_ASSISTANT_URL', 'http://ha')
os.environ.setdefault('HOME_ASSISTANT_TOKEN', 'token')
os.environ.setdefault('OLLAMA_URL', 'http://x')
os.environ.setdefault('OLLAMA_MODEL', 'llama3')

from app.skills.smalltalk_skill import GREETINGS, SmalltalkSkill, is_greeting
from app import router, skills


def test_is_greeting():
    assert is_greeting('hi')
    assert is_greeting('yo!')
    assert is_greeting('HELLO?')
    assert not is_greeting("what's new")


def test_handle_returns_valid_format():
    s = SmalltalkSkill()

    class User:
        last_project = 'garage build'

    resp = s.handle('hello', User())
    assert resp is not None
    assert any(resp.startswith(g) for g in GREETINGS)
    assert resp.endswith('?')


def test_router_integration():
    result = asyncio.run(router.route_prompt('hello'))
    assert any(result.startswith(g) for g in GREETINGS)
