from __future__ import annotations

import os

from fastapi.testclient import TestClient

from app.main import app


def _run_trace(client: TestClient, q: str) -> dict:
    r = client.get("/v1/admin/retrieval/trace", params={"q": q, "k": 5})
    assert r.status_code == 200
    return r.json()


def test_ablation_modes(monkeypatch):
    # Fake the base memories so we don't need a real vector store
    from app.memory import vector_store as vs

    def _fake(user_id: str, prompt: str, k: int | None = None, filters=None):
        seed = prompt.split()[0]
        return [f"{seed} doc {i}" for i in range(10)][: (k or 5)]

    monkeypatch.setattr(vs, "safe_query_user_memories", _fake)
    client = TestClient(app)

    os.environ["USE_RETRIEVAL_PIPELINE"] = "1"

    # base
    os.environ["USE_MMR"] = "0"
    os.environ["RERANK_CASCADE"] = "0"
    base = _run_trace(client, "base prompt")

    # +MMR
    os.environ["USE_MMR"] = "1"
    mmr = _run_trace(client, "mmr prompt")

    # +HyDE (placeholder flag; pipeline currently uses same trace path)
    os.environ["USE_HYDE"] = "1"
    hyde = _run_trace(client, "hyde prompt")

    # +Cascade
    os.environ["RERANK_CASCADE"] = "1"
    cascade = _run_trace(client, "cascade prompt")

    assert isinstance(base.get("items"), list)
    assert isinstance(mmr.get("items"), list)
    assert isinstance(hyde.get("items"), list)
    assert isinstance(cascade.get("items"), list)


