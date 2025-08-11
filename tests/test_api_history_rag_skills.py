import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_history_recent_reads_jsonl(monkeypatch, tmp_path: Path):
    # point history file to temp jsonl
    from app.api import history as api_history
    import app.history as hist

    p = tmp_path / "history.jsonl"
    monkeypatch.setattr(hist, "HISTORY_FILE", p)
    # also patch the value captured in the api module at import time
    monkeypatch.setattr(api_history, "HISTORY_FILE", p)
    p.write_text("\n".join([
        "{}",
        '{"type":"capture","x":1}',
        '{"type":"capture","x":2}',
    ]))

    app = FastAPI()
    app.include_router(api_history.router)
    client = TestClient(app)
    r = client.get("/history/recent", params={"limit": 2})
    assert r.status_code == 200
    items = r.json()["items"]
    # last two valid dict lines returned (oldest first)
    assert len(items) == 2 and items[0]["x"] == 1 and items[1]["x"] == 2


def test_rag_search_works_without_store(monkeypatch):
    # Force import path where _safe_query is None
    from importlib import reload
    import app.api.rag as api_rag

    app = FastAPI()
    app.include_router(api_rag.router)
    client = TestClient(app)
    r = client.get("/rag/search", params={"q": "hi", "k": 3})
    assert r.status_code == 200
    assert r.json()["items"] == []


def test_skills_list_shape(monkeypatch):
    # Build against real skills catalog but only validate shape
    from app.api import skills as api_skills

    app = FastAPI()
    app.include_router(api_skills.router)
    client = TestClient(app)
    r = client.get("/skills/list")
    assert r.status_code == 200
    data = r.json()
    assert "items" in data
    if data["items"]:
        it = data["items"][0]
        assert "name" in it and "keywords" in it


