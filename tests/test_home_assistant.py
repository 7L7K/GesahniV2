import sys, os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import pytest

import asyncio


def test_handle_command_entity_not_found(monkeypatch):
    os.environ["HOME_ASSISTANT_URL"] = "http://ha"
    os.environ["HOME_ASSISTANT_TOKEN"] = "token"
    from app import home_assistant

    async def fake_states():
        return []

    monkeypatch.setattr(home_assistant, "get_states", fake_states)
    res = asyncio.run(home_assistant.handle_command("turn on kitchen"))
    assert res == {"error": "entity_not_found", "name": "kitchen"}
