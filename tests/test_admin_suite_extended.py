import asyncio
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


def test_metrics_allows_without_token_in_tests():
    client = make_client()
    r = client.get("/v1/admin/metrics")
    # Under tests we allow omitted token
    assert r.status_code == 200


def test_metrics_cache_rate_is_float_under_pytest():
    client = make_client()
    r = client.get("/v1/admin/metrics?token=t")
    assert r.status_code == 200
    assert isinstance(r.json().get("cache_hit_rate"), (float, int))


def test_router_decisions_limit_bounds():
    client = make_client()
    assert client.get("/v1/admin/router/decisions?limit=0&token=t").status_code == 422
    assert client.get("/v1/admin/router/decisions?limit=1001&token=t").status_code == 422


def test_retrieval_last_limit_bounds():
    client = make_client()
    assert client.get("/v1/admin/retrieval/last?limit=0&token=t").status_code == 422
    assert client.get("/v1/admin/retrieval/last?limit=2001&token=t").status_code == 422


def test_router_decisions_order_and_fields():
    from app.decisions import add_decision
    add_decision({"req_id": "a", "engine_used": "gpt", "model_name": "gpt-4o", "route_reason": "default", "latency_ms": 12})
    add_decision({"req_id": "b", "engine_used": "llama", "model_name": "llama3", "route_reason": "cheap", "latency_ms": 5, "cache_hit": True, "cache_similarity": 0.91, "self_check_score": 0.8})
    client = make_client()
    r = client.get("/v1/admin/router/decisions?limit=1&token=t")
    body = r.json()
    items = body.get("items")
    # first page contains newest
    assert [it["req_id"] for it in items] == ["b"]
    assert set(["engine", "model", "route_reason", "latency_ms", "cache_hit"]).issubset(items[0].keys())
    # pagination cursor and second page order
    nc = body.get("next_cursor")
    assert nc in (None, 1)
    if nc:
        r2 = client.get(f"/v1/admin/router/decisions?limit=1&cursor={nc}&token=t")
        body2 = r2.json()
        items2 = body2.get("items")
        assert [it["req_id"] for it in items2] == ["a"]


def test_retrieval_last_filters_trace_event():
    from app.decisions import add_decision, add_trace_event
    add_decision({"req_id": "r1"})
    add_decision({"req_id": "r2"})
    add_trace_event("r2", "retrieval_trace", ok=True)
    client = make_client()
    r = client.get("/v1/admin/retrieval/last?limit=5&token=t")
    ids = [it["req_id"] for it in r.json().get("items", [])]
    assert "r2" in ids and "r1" not in ids


def test_decisions_explain_ok():
    from app.decisions import add_decision
    add_decision({"req_id": "xyz", "engine_used": "gpt"})
    client = make_client()
    r = client.get("/v1/admin/decisions/explain?req_id=xyz&token=t")
    assert r.status_code == 200
    body = r.json()
    assert body["req_id"] == "xyz"


def test_errors_limit_and_shape():
    from app.logging_config import _ERRORS  # type: ignore
    # seed errors
    _ERRORS.clear()
    for i in range(60):
        _ERRORS.append({"timestamp": "t", "level": "ERROR", "component": "x", "msg": str(i)})
    client = make_client()
    r = client.get("/v1/admin/errors?token=t")
    assert r.status_code == 200
    errs = r.json().get("errors")
    assert len(errs) == 50 and errs[-1]["msg"] == "59"


def test_self_review_unavailable_shape():
    client = make_client()
    r = client.get("/v1/admin/self_review?token=t")
    assert r.status_code == 200
    assert isinstance(r.json(), dict)


def test_flags_endpoint_sets_env_and_guard():
    client = make_client()
    assert client.post("/v1/admin/flags?key=FOO&value=BAR&token=x").status_code == 403
    r = client.post("/v1/admin/flags?key=FOO&value=BAR&token=t")
    assert r.status_code == 200
    assert os.environ.get("FOO") == "BAR"


def test_admin_config_403_without_token_when_not_test_mode(monkeypatch):
    client = make_client()
    # simulate production-like (PYTEST_RUNNING unset)
    monkeypatch.delenv("PYTEST_RUNNING", raising=False)
    # if ADMIN_TOKEN set, missing/incorrect token is forbidden
    assert client.get("/v1/admin/config").status_code == 403
    assert client.get("/v1/admin/config?token=x").status_code == 403


def test_admin_config_ok_with_token_and_overrides(monkeypatch):
    client = make_client()
    os.environ["VECTOR_STORE"] = "dual"
    os.environ["QDRANT_COLLECTION"] = "kb:abc"
    r = client.get("/v1/admin/config?token=t")
    assert r.status_code == 200
    data = r.json()
    assert data["store"]["active_collection"] == "kb:abc"


def test_admin_metrics_top_skills_sorted():
    from app.analytics import record_skill
    # increment skills asynchronously
    asyncio.run(record_skill("a"))
    asyncio.run(record_skill("b"))
    asyncio.run(record_skill("b"))
    client = make_client()
    r = client.get("/v1/admin/metrics?token=t")
    skills = r.json().get("top_skills")
    assert skills and skills[0][0] == "b" and skills[0][1] >= skills[-1][1]


def test_admin_router_decisions_clip_limit():
    from app.decisions import add_decision
    for i in range(10):
        add_decision({"req_id": f"id{i}"})
    client = make_client()
    r = client.get("/v1/admin/router/decisions?limit=3&token=t")
    assert len(r.json().get("items")) == 3


def test_admin_retrieval_last_clip_limit():
    from app.decisions import add_decision, add_trace_event
    for i in range(10):
        rid = f"rid{i}"
        add_decision({"req_id": rid})
        add_trace_event(rid, "retrieval_trace", ok=True)
    client = make_client()
    r = client.get("/v1/admin/retrieval/last?limit=4&token=t")
    assert len(r.json().get("items")) == 4


def test_admin_decisions_explain_404_for_missing():
    client = make_client()
    assert client.get("/v1/admin/decisions/explain?req_id=missing&token=t").status_code == 404


