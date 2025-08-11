import pytest


@pytest.mark.parametrize(
    "prompt,intent,tokens,expect_engine",
    [
        ("do heavy research on climate change" + " words" * 40, "analysis", 50, "gpt"),
        ("please explain", "chat", 2000, "gpt"),
        ("write code sample", "chat", 10, "gpt"),
    ],
)
def test_pick_model_gpt_paths(monkeypatch, prompt, intent, tokens, expect_engine):
    from app import model_picker
    from app import llama_integration

    monkeypatch.setattr(llama_integration, "LLAMA_HEALTHY", True)
    monkeypatch.setattr(llama_integration, "llama_circuit_open", False)
    monkeypatch.setenv("MODEL_ROUTER_HEAVY_WORDS", "30")
    engine, model = model_picker.pick_model(prompt, intent, tokens)
    assert engine == expect_engine


def test_pick_model_llama_path(monkeypatch):
    from app import model_picker
    from app import llama_integration

    monkeypatch.setattr(llama_integration, "LLAMA_HEALTHY", True)
    monkeypatch.setattr(llama_integration, "llama_circuit_open", False)
    monkeypatch.setenv("OLLAMA_MODEL", "llama3:latest")

    prompt = "short prompt"
    engine, model = model_picker.pick_model(prompt, "chat", 10)
    assert engine == "llama"


