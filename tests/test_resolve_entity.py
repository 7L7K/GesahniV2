import asyncio

import app.home_assistant as ha


def setup_env(monkeypatch):
    monkeypatch.setenv("HOME_ASSISTANT_URL", "http://ha")
    monkeypatch.setenv("HOME_ASSISTANT_TOKEN", "token")


def test_exact_match_preferred(monkeypatch):
    setup_env(monkeypatch)

    async def fake_states():
        return [
            {
                "entity_id": "light.kitchen",
                "attributes": {"friendly_name": "Kitchen"},
            },
            {
                "entity_id": "light.kitchenette",
                "attributes": {"friendly_name": "Kitchenette"},
            },
        ]

    monkeypatch.setattr(ha, "get_states", fake_states)
    result = asyncio.run(ha.resolve_entity("Kitchen"))
    assert result == ["light.kitchen"]


def test_substring_fallback(monkeypatch):
    setup_env(monkeypatch)

    async def fake_states():
        return [
            {
                "entity_id": "switch.coffee",
                "attributes": {"friendly_name": "Coffee Maker"},
            }
        ]

    monkeypatch.setattr(ha, "get_states", fake_states)
    result = asyncio.run(ha.resolve_entity("coffee"))
    assert result == ["switch.coffee"]


def test_get_states_cache_and_invalidate(monkeypatch):
    setup_env(monkeypatch)
    ha.invalidate_states_cache()

    calls = {"states": 0}

    async def fake_request(method, path, json=None, timeout=10.0):
        if path == "/states":
            calls["states"] += 1
            return [
                {
                    "entity_id": "light.kitchen",
                    "attributes": {"friendly_name": "Kitchen"},
                }
            ]
        return {}

    monkeypatch.setattr(ha, "_request", fake_request)

    async def run():
        await ha.resolve_entity("Kitchen")
        await ha.resolve_entity("Kitchen")
        assert calls["states"] == 1
        await ha.call_service("light", "turn_on", {"entity_id": "light.kitchen"})
        await ha.resolve_entity("Kitchen")
        assert calls["states"] == 2

    asyncio.run(run())
