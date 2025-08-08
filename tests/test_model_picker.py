import os

os.environ["OLLAMA_MODEL"] = "llama3"
os.environ.setdefault("OLLAMA_URL", "http://localhost:11434")

from app.model_picker import pick_model, GPT_DEFAULT_MODEL
from app import llama_integration


def test_pick_model_llama():
    engine, model = pick_model("hello", "chat", 5)
    assert engine == "llama"
    assert model == llama_integration.OLLAMA_MODEL or model == "llama3"

def test_pick_model_complex_long():
    prompt = "word " * 31
    engine, model = pick_model(prompt, "chat", 0)
    assert engine == "gpt"
    assert model == GPT_DEFAULT_MODEL

def test_pick_model_keyword():
    engine, model = pick_model("please analyze this", "chat", 0)
    assert engine == "gpt"
    assert model == GPT_DEFAULT_MODEL

def test_pick_model_llama_unhealthy(monkeypatch):
    monkeypatch.setattr(llama_integration, "LLAMA_HEALTHY", False)
    engine, model = pick_model("hello", "chat", 5)
    assert engine == "gpt"
    assert model == GPT_DEFAULT_MODEL
