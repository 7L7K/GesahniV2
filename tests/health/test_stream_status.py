import os
import sys

from fastapi import HTTPException
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def setup_app(monkeypatch):
    os.environ["OLLAMA_URL"] = "http://x"
    os.environ["OLLAMA_MODEL"] = "llama3"
    os.environ["HOME_ASSISTANT_URL"] = "http://ha"
    os.environ["HOME_ASSISTANT_TOKEN"] = "token"
    from app import main

    monkeypatch.setattr(main, "ha_startup", lambda: None)
    monkeypatch.setattr(main, "llama_startup", lambda: None)
    return main


def test_streaming_sets_status_code(monkeypatch):
    main = setup_app(monkeypatch)

    # Stub the legacy compat router entrypoint that /ask uses
    class DummyRouter:
        async def route_prompt(self, payload):  # payload is dict
            raise HTTPException(status_code=418, detail="teapot")

    def fake_get_router():
        return DummyRouter()

    # Patch the registry getter used by app.router.compat_api.ask_compat
    monkeypatch.setattr("app.router.registry.get_router", fake_get_router)

    client = TestClient(main.app)
    resp = client.post("/ask", json={"prompt": "hi"})
    # Legacy /ask compat endpoint normalizes upstream errors to 503
    assert resp.status_code == 503
    data = resp.json()
    assert isinstance(data, dict)
    assert data.get("code") in {"BACKEND_UNAVAILABLE", "ROUTER_UNAVAILABLE"}
