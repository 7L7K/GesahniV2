import os
import sys
import asyncio
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_handle_command_entity_not_found(monkeypatch):
    os.environ["HOME_ASSISTANT_URL"] = "http://ha"
    os.environ["HOME_ASSISTANT_TOKEN"] = "token"
    from app import home_assistant

    async def fake_states():
        return []

    monkeypatch.setattr(home_assistant, "get_states", fake_states)
    res = asyncio.run(home_assistant.handle_command("turn on kitchen"))
    assert res == home_assistant.CommandResult(
        success=False, message="entity_not_found", data={"name": "kitchen"}
    )


def test_get_states_unreachable(monkeypatch):
    os.environ["HOME_ASSISTANT_URL"] = "http://ha"
    os.environ["HOME_ASSISTANT_TOKEN"] = "token"
    from app import home_assistant

    async def fake_request(method, path, json=None, timeout=10.0):
        raise RuntimeError("boom")

    monkeypatch.setattr(home_assistant, "_request", fake_request)
    with pytest.raises(home_assistant.HomeAssistantAPIError):
        asyncio.run(home_assistant.get_states())


def test_resolve_entity_unreachable(monkeypatch):
    os.environ["HOME_ASSISTANT_URL"] = "http://ha"
    os.environ["HOME_ASSISTANT_TOKEN"] = "token"
    from app import home_assistant

    async def fake_states():
        raise home_assistant.HomeAssistantAPIError("nope")

    monkeypatch.setattr(home_assistant, "get_states", fake_states)
    res = asyncio.run(home_assistant.resolve_entity("kitchen"))
    assert res == []
