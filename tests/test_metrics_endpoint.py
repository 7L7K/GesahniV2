import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from fastapi.testclient import TestClient


def test_metrics_endpoint(monkeypatch):
    os.environ["OLLAMA_URL"] = "http://x"
    os.environ["OLLAMA_MODEL"] = "llama3"
    os.environ["HOME_ASSISTANT_URL"] = "http://ha"
    os.environ["HOME_ASSISTANT_TOKEN"] = "token"

    from app import home_assistant, llama_integration, main, router
    from app.telemetry import log_record_var

    monkeypatch.setattr(home_assistant, "startup_check", lambda: None)
    monkeypatch.setattr(llama_integration, "startup_check", lambda: None)

    async def fake_route(prompt, model=None, user_id="u"):
        rec = log_record_var.get()
        if rec:
            rec.engine_used = "gpt"
            rec.prompt_cost_usd = 0.1
            rec.cost_usd = 0.1
        return "ok"

    monkeypatch.setattr(router, "route_prompt", fake_route)

    client = TestClient(main.app)
    client.post("/ask", json={"prompt": "hi"})
    resp = client.get("/metrics")
    assert resp.status_code == 200
    text = resp.text
    assert "app_request_total" in text
    assert "app_request_latency_seconds" in text
    assert "app_request_cost_usd" in text
