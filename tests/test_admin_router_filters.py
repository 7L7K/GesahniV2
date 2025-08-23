import os

from fastapi import FastAPI
from fastapi.testclient import TestClient


def make_client():
    from app.api.admin import router as admin_router

    app = FastAPI()
    app.include_router(admin_router, prefix="/v1")
    return TestClient(app)


def setup_function(_):
    os.environ["ADMIN_TOKEN"] = "t"
    os.environ["PYTEST_RUNNING"] = "1"


def test_router_filters_and_pagination():
    from app.decisions import add_decision

    add_decision(
        {
            "req_id": "f1",
            "engine_used": "gpt",
            "model_name": "gpt-4o",
            "route_reason": "default",
            "cache_hit": False,
            "intent": "chat",
        }
    )
    add_decision(
        {
            "req_id": "f2",
            "engine_used": "llama",
            "model_name": "llama3",
            "route_reason": "cheap path",
            "cache_hit": True,
            "intent": "search",
        }
    )
    add_decision(
        {
            "req_id": "f3",
            "engine_used": "gpt",
            "model_name": "gpt-4o-mini",
            "route_reason": "fallback",
            "cache_hit": False,
            "intent": "search",
        }
    )

    client = make_client()
    # filter by engine
    r = client.get("/v1/admin/router/decisions?engine=gpt&token=t")
    assert all(it.get("engine") == "gpt" for it in r.json().get("items", []))
    # filter by model substring
    r = client.get("/v1/admin/router/decisions?model=mini&token=t")
    assert all("mini" in (it.get("model") or "") for it in r.json().get("items", []))
    # filter by cache_hit
    r = client.get("/v1/admin/router/decisions?cache_hit=true&token=t")
    assert all(bool(it.get("cache_hit")) is True for it in r.json().get("items", []))
    # filter by intent and q in reason
    r = client.get("/v1/admin/router/decisions?intent=search&q=cheap&token=t")
    items = r.json().get("items", [])
    assert all(
        "search" in (it.get("intent") or "").lower()
        and "cheap" in (it.get("route_reason") or "").lower()
        for it in items
    )
    # pagination via cursor
    r1 = client.get("/v1/admin/router/decisions?limit=1&token=t")
    nc = r1.json().get("next_cursor")
    assert nc in (None, 1)
    if nc:
        r2 = client.get(f"/v1/admin/router/decisions?limit=1&cursor={nc}&token=t")
        assert r2.status_code == 200
