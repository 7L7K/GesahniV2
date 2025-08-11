import os
from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_admin_config_guard_and_shape():
    os.environ["ADMIN_TOKEN"] = "t"
    from app.api.admin import router as admin_router
    app = FastAPI()
    app.include_router(admin_router, prefix="/v1")
    client = TestClient(app)

    assert client.get("/v1/admin/config?token=x").status_code == 403
    r = client.get("/v1/admin/config?token=t")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, dict)
    assert "store" in data and isinstance(data["store"], dict)


def test_admin_config_flags_reflected(monkeypatch):
    from app.main import app
    # Tests force in-memory vector store; we only verify that /admin/config reflects the env overrides
    monkeypatch.setenv("VECTOR_STORE", "qdrant")
    monkeypatch.setenv("QDRANT_COLLECTION", "kb:test")
    monkeypatch.setenv("USE_HYDE", "1")
    monkeypatch.setenv("USE_MMR", "1")
    monkeypatch.setenv("TOPK_VEC", "50")
    monkeypatch.setenv("TOPK_FINAL", "8")
    monkeypatch.setenv("RERANK_CASCADE", "1")
    monkeypatch.setenv("RERANK_LOCAL_MODEL", "minilm")
    monkeypatch.setenv("RERANK_HOSTED", "voyage")
    monkeypatch.setenv("RERANK_GATE_LOW", "0.2")
    monkeypatch.setenv("MEM_WRITE_QUOTA_PER_SESSION", "42")
    monkeypatch.setenv("MEM_IMPORTANCE_TAU", "0.7")
    monkeypatch.setenv("MEM_NOVELTY_TAU", "0.55")
    monkeypatch.setenv("TRACE_SAMPLE_RATE", "0.2")
    monkeypatch.setenv("LATENCY_BUDGET_MS", "900")
    monkeypatch.setenv("ABLATION_FLAGS", "hyde,mmr,cascade")

    client = TestClient(app)
    r = client.get("/v1/admin/config")
    assert r.status_code == 200
    cfg = r.json()
    # Endpoint overlays env; vector_store should reflect our override even if tests force memory backend
    assert cfg["store"]["vector_store"] == "qdrant"
    assert cfg["retrieval"]["use_mmr"] is True and cfg["retrieval"]["topk_vec"] == 50
    assert cfg["rerank"]["cascade"] is True and cfg["rerank"]["hosted"] == "voyage"
    assert cfg["memgpt"]["write_quota_per_session"] == 42
    assert "hyde" in cfg["obs"]["ablation_flags"]


