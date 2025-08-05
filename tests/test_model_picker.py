import os

os.environ["OLLAMA_MODEL"] = "llama3"

from app.model_picker import pick_model, GPT_DEFAULT_MODEL
from app.llama_integration import OLLAMA_MODEL


def test_pick_model_llama():
    engine, model = pick_model("hello", "chat", 5)
    assert engine == "llama"
    assert model == OLLAMA_MODEL or model == "llama3"


def test_pick_model_complex_long():
    prompt = "word " * 31
    engine, model = pick_model(prompt, "chat", 0)
    assert engine == "gpt"
    assert model == GPT_DEFAULT_MODEL


def test_pick_model_keyword():
    engine, model = pick_model("please analyze this", "chat", 0)
    assert engine == "gpt"
    assert model == GPT_DEFAULT_MODEL
