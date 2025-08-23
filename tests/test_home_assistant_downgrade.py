from fastapi.testclient import TestClient


def test_ha_service_human_readable(monkeypatch):
    import os

    from app import home_assistant as ha
    from app.main import app
    from app.security import rate_limit, verify_token

    # Disable auth for this test by monkeypatching verify_token to no-op
    async def _noop():
        return None

    app.dependency_overrides[verify_token] = _noop
    app.dependency_overrides[rate_limit] = _noop
    # Ensure scope enforcement is disabled
    os.environ["JWT_SECRET"] = ""

    async def fake_call(domain, service, data):
        raise ha.HomeAssistantAPIError("confirm_required")

    monkeypatch.setattr(ha, "call_service", fake_call)
    client = TestClient(app)
    res = client.post("/v1/ha/service", json={"domain": "light", "service": "toggle", "data": {"entity_id": "light.k"}})
    print(res.status_code, res.text)
    # Handler wraps as 500 with readable message
    assert res.status_code == 500
    assert res.json()["detail"] == "Home Assistant error"

