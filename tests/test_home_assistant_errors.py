import asyncio
import os


def test_ha_error_taxonomy(monkeypatch):
    os.environ["HOME_ASSISTANT_URL"] = "http://ha"
    os.environ["HOME_ASSISTANT_TOKEN"] = "x"
    from app import home_assistant as ha

    async def fake_req(method, path, json=None, timeout=10.0):
        raise ha.HomeAssistantAPIError("unauthorized")

    monkeypatch.setattr(ha, "_request", fake_req)

    try:
        asyncio.run(ha.call_service("light", "toggle", {"entity_id": "light.k"}))
    except ha.HomeAssistantAPIError as e:
        assert str(e) in {"unauthorized", "confirm_required", "not_found", "timeout", "http_error"}


