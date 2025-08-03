import os, sys, json, asyncio
from fastapi.testclient import TestClient
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def setup_app(monkeypatch, hist_path):
    os.environ["OLLAMA_URL"] = "http://x"
    os.environ["OLLAMA_MODEL"] = "llama3"
    os.environ["HOME_ASSISTANT_URL"] = "http://ha"
    os.environ["HOME_ASSISTANT_TOKEN"] = "token"
    os.environ["OPENAI_API_KEY"] = "key"
    from app import main
    monkeypatch.setattr(main, "ha_startup", lambda: None)
    monkeypatch.setattr(main, "llama_startup", lambda: None)
    monkeypatch.setattr("app.history.HISTORY_FILE", hist_path)
    async def fake_route(prompt: str, model=None):
        from app.prompt_builder import PromptBuilder
        from app.telemetry import log_record_var
        PromptBuilder.build(prompt, session_id="s", user_id="u")
        rec = log_record_var.get()
        if rec:
            rec.cache_hit = False
        return "ok"
    monkeypatch.setattr(main, "route_prompt", fake_route)
    return TestClient(main.app)


def test_telemetry_logged(monkeypatch, tmp_path):
    hist = tmp_path / "hist.jsonl"
    client = setup_app(monkeypatch, str(hist))
    from app import prompt_builder, analytics
    analytics._latency_samples = []
    monkeypatch.setattr(prompt_builder.memgpt, "summarize_session", lambda sid: "")
    monkeypatch.setattr(
        prompt_builder, "query_user_memories", lambda q, k=5: ["m1", "m2"]
    )
    resp = client.post("/ask", json={"prompt": "hi"})
    assert resp.status_code == 200
    line = hist.read_text().splitlines()[-1]
    data = json.loads(line)
    from app.prompt_builder import _count_tokens
    assert data["status"] == "OK"
    assert data["latency_ms"] >= 0
    assert data["embed_tokens"] == _count_tokens("hi")
    assert data["retrieval_count"] == 2
    assert data["cache_hit"] is False
    assert data["p95_latency_ms"] == data["latency_ms"]


def test_latency_p95(monkeypatch):
    from app import analytics
    analytics._latency_samples = []
    for val in [10, 20, 30, 40, 50]:
        asyncio.run(analytics.record_latency(val))
    assert analytics.latency_p95() == 50
