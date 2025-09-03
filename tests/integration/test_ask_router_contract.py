import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_ask_returns_503_when_router_missing(authed_client):
    # Ensure router is unset
    try:
        from app.router import registry

        registry._router = None
    except Exception:
        pass

    r = await authed_client.post("/ask", json={"prompt": "hi"})
    assert r.status_code == 503
    body = r.json()
    assert body.get("code") in {"ROUTER_UNAVAILABLE", "BACKEND_UNAVAILABLE"}


@pytest.mark.asyncio
async def test_ask_returns_503_when_router_raises(monkeypatch, authed_client):
    from app.router import registry

    class Boom:
        async def route_prompt(self, *_args, **_kwargs):
            raise RuntimeError("llm down")

    registry.set_router(Boom())

    r = await authed_client.post("/ask", json={"prompt": "yo"})

    assert r.status_code == 503
    body = r.json()
    assert body.get("code") == "BACKEND_UNAVAILABLE"


@pytest.mark.asyncio
async def test_ask_returns_200_when_router_works(monkeypatch, authed_client):
    from app.router import registry

    class Good:
        async def route_prompt(self, payload):
            return {"response": "ok"}

    registry.set_router(Good())

    r = await authed_client.post("/ask", json={"prompt": "hello"})

    assert r.status_code == 200
    body = r.json()
    assert body.get("response") == "ok"
