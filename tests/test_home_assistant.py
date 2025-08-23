import asyncio
import os
import sys

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


def test_resolve_entity_unreachable(monkeypatch):
    os.environ["HOME_ASSISTANT_URL"] = "http://ha"
    os.environ["HOME_ASSISTANT_TOKEN"] = "token"
    from app import home_assistant

    async def fake_states():
        raise home_assistant.HomeAssistantAPIError("nope")

    monkeypatch.setattr(home_assistant, "get_states", fake_states)
    res = asyncio.run(home_assistant.resolve_entity("kitchen"))
    assert res == []


def test_request_picks_up_token(monkeypatch):
    monkeypatch.delenv("HOME_ASSISTANT_TOKEN", raising=False)
    os.environ["HOME_ASSISTANT_URL"] = "http://ha"
    import importlib

    from app import home_assistant

    importlib.reload(home_assistant)

    captured: dict[str, dict] = {}

    async def fake_json_request(method, url, headers, json, timeout):  # type: ignore[override]
        captured["headers"] = headers
        return {}, None

    monkeypatch.setattr(home_assistant, "json_request", fake_json_request)

    home_assistant.HOME_ASSISTANT_TOKEN = "newtoken"

    asyncio.run(home_assistant._request("GET", "/states"))

    assert captured["headers"]["Authorization"] == "Bearer newtoken"
