import asyncio
import logging

from app import llama_integration


def test_missing_model_warns(monkeypatch, caplog):
    monkeypatch.setenv("OLLAMA_URL", "http://x")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")
    llama_integration.OLLAMA_URL = "http://x"
    llama_integration.OLLAMA_MODEL = "llama3"

    async def fake_json_request(method, url, **kwargs):
        return {"models": ["other"]}, None

    monkeypatch.setattr(llama_integration, "json_request", fake_json_request)

    with caplog.at_level(logging.WARNING):
        asyncio.run(llama_integration._check_and_set_flag())

    assert "missing on Ollama" in caplog.text
