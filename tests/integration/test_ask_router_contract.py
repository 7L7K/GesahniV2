import pytest


@pytest.mark.asyncio
async def test_ask_returns_503_when_router_missing(authed_client):
    # Ensure router is unset
    try:
        from app.router.registry import get_router, set_router

        registry = type(
            "MockRegistry",
            (),
            {"_router": None, "set_router": set_router, "get_router": get_router},
        )()

        registry._router = None
    except Exception:
        pass

    r = await authed_client.post("/ask", json={"prompt": "hi"})
    assert r.status_code == 503
    body = r.json()
    assert body.get("code") in {"router_unavailable", "backend_unavailable"}


@pytest.mark.asyncio
async def test_ask_returns_503_when_router_raises(monkeypatch, authed_client):
    from app.router.registry import set_router

    class Boom:
        async def route_prompt(self, *_args, **_kwargs):
            raise RuntimeError("llm down")

    set_router(Boom())

    r = await authed_client.post("/ask", json={"prompt": "yo"})

    assert r.status_code == 503
    body = r.json()
    assert body.get("code") == "backend_unavailable"


@pytest.mark.asyncio
async def test_ask_returns_200_when_router_works(monkeypatch, authed_client):
    from app.router.registry import set_router

    class Good:
        async def route_prompt(self, payload):
            return {"response": "ok"}

    set_router(Good())

    r = await authed_client.post("/ask", json={"prompt": "hello"})

    assert r.status_code == 200
    body = r.json()
    assert body.get("response") == "ok"
