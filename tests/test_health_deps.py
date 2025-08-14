from fastapi.testclient import TestClient

from app.main import app
import app.health_utils as hu


def test_health_deps_degraded_llama(monkeypatch):
    async def llama_err():
        return "error"

    async def ha_skip():
        return "skipped"

    async def q_ok():
        return "ok"

    monkeypatch.setattr(hu, "check_llama", llama_err)
    monkeypatch.setattr(hu, "check_home_assistant", ha_skip)
    monkeypatch.setattr(hu, "check_qdrant", q_ok)
    monkeypatch.setattr(hu, "check_spotify", ha_skip)

    c = TestClient(app)
    r = c.get("/healthz/deps")
    assert r.status_code == 200
    body = r.json()
    assert body.get("status") == "degraded"
    checks = body.get("checks") or {}
    assert checks.get("backend") == "ok"
    assert checks.get("llama") == "error"
    assert checks.get("ha") == "skipped"


def test_health_deps_skipped_when_env_missing(monkeypatch):
    async def skip():
        return "skipped"

    monkeypatch.setattr(hu, "check_llama", skip)
    monkeypatch.setattr(hu, "check_home_assistant", skip)
    monkeypatch.setattr(hu, "check_qdrant", skip)
    monkeypatch.setattr(hu, "check_spotify", skip)
    c = TestClient(app)
    r = c.get("/healthz/deps")
    assert r.status_code == 200
    body = r.json()
    assert body.get("status") == "ok"  # all skipped is not degraded
    assert set((body.get("checks") or {}).keys()) >= {"backend", "llama", "ha", "qdrant", "spotify"}


