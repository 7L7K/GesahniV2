import os, sys
import pytest
os.environ.setdefault("HOME_ASSISTANT_URL", "http://test")
os.environ.setdefault("HOME_ASSISTANT_TOKEN", "token")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.home_assistant import resolve_entities

@pytest.mark.asyncio
async def test_home_assistant_room_synonym(monkeypatch):
    async def mock_get_states():
        return [
            {"entity_id":"light.living_room", "attributes":{"friendly_name":"Living Room Light"}},
        ]
    monkeypatch.setattr("app.home_assistant.get_states", mock_get_states)
    entities = await resolve_entities("lounge")
    assert "light.living_room" in entities
