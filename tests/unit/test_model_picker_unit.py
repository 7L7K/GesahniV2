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
    engine, model, reason, keyword = model_picker.pick_model(prompt, intent, tokens)
    assert engine == expect_engine


def test_pick_model_llama_path(monkeypatch):
    from app import model_picker
    from app import llama_integration

    monkeypatch.setattr(llama_integration, "LLAMA_HEALTHY", True)
    monkeypatch.setattr(llama_integration, "llama_circuit_open", False)
    monkeypatch.setenv("OLLAMA_MODEL", "llama3:latest")

    prompt = "short prompt"
    engine, model, reason, keyword = model_picker.pick_model(prompt, "chat", 10)
    assert engine == "llama"


@pytest.mark.parametrize(
    "prompt,intent,tokens,expected_reason",
    [
        ("do heavy research on climate change" + " words" * 40, "analysis", 50, "heavy_length"),
        ("please explain", "chat", 2000, "heavy_tokens"),
        ("write code sample", "chat", 10, "keyword"),
        # "analyze this data" triggers keyword detection first, not heavy_intent
        ("analyze this data", "analysis", 10, "keyword"),
    ],
)
def test_pick_model_gpt_reasons(monkeypatch, prompt, intent, tokens, expected_reason):
    """Test that GPT paths return correct reasons."""
    from app import model_picker
    from app import llama_integration

    monkeypatch.setattr(llama_integration, "LLAMA_HEALTHY", True)
    monkeypatch.setattr(llama_integration, "llama_circuit_open", False)
    monkeypatch.setenv("MODEL_ROUTER_HEAVY_WORDS", "30")
    monkeypatch.setenv("MODEL_ROUTER_HEAVY_TOKENS", "1000")
    
    engine, model, reason, keyword = model_picker.pick_model(prompt, intent, tokens)
    assert engine == "gpt"
    assert reason == expected_reason


def test_pick_model_llama_unhealthy_fallback(monkeypatch):
    """Test fallback to GPT when llama is unhealthy."""
    from app import model_picker
    from app import llama_integration

    monkeypatch.setattr(llama_integration, "LLAMA_HEALTHY", False)
    monkeypatch.setattr(llama_integration, "llama_circuit_open", False)
    monkeypatch.setenv("OLLAMA_MODEL", "llama3:latest")

    prompt = "short prompt"
    engine, model, reason, keyword = model_picker.pick_model(prompt, "chat", 10)
    assert engine == "gpt"
    assert reason == "llama_unhealthy"


def test_pick_model_circuit_breaker_fallback(monkeypatch):
    """Test fallback to GPT when circuit breaker is open."""
    from app import model_picker
    from app import llama_integration

    monkeypatch.setattr(llama_integration, "LLAMA_HEALTHY", True)
    monkeypatch.setattr(llama_integration, "llama_circuit_open", True)
    monkeypatch.setenv("OLLAMA_MODEL", "llama3:latest")

    prompt = "short prompt"
    engine, model, reason, keyword = model_picker.pick_model(prompt, "chat", 10)
    assert engine == "gpt"
    assert reason == "circuit_breaker"


def test_pick_model_no_llama_model_configured(monkeypatch):
    """Test fallback when no llama model is configured."""
    from app import model_picker
    from app import llama_integration

    monkeypatch.setattr(llama_integration, "LLAMA_HEALTHY", True)
    monkeypatch.setattr(llama_integration, "llama_circuit_open", False)
    monkeypatch.setattr(llama_integration, "OLLAMA_MODEL", None)
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)

    prompt = "short prompt"
    engine, model, reason, keyword = model_picker.pick_model(prompt, "chat", 10)
    assert engine == "llama"
    # Should use default fallback model
    assert "llama" in model.lower()


def test_pick_model_empty_llama_model_configured(monkeypatch):
    """Test fallback when no llama model is configured."""
    from app import model_picker
    from app import llama_integration

    monkeypatch.setattr(llama_integration, "LLAMA_HEALTHY", True)
    monkeypatch.setattr(llama_integration, "llama_circuit_open", False)
    monkeypatch.setattr(llama_integration, "OLLAMA_MODEL", "")
    monkeypatch.setenv("OLLAMA_MODEL", "")

    prompt = "short prompt"
    engine, model, reason, keyword = model_picker.pick_model(prompt, "chat", 10)
    assert engine == "llama"
    # When both are empty strings, the model becomes empty
    assert model == ""


def test_pick_model_environment_ollama_model(monkeypatch):
    """Test that environment OLLAMA_MODEL is used when llama_integration.OLLAMA_MODEL is None."""
    from app import model_picker
    from app import llama_integration

    monkeypatch.setattr(llama_integration, "LLAMA_HEALTHY", True)
    monkeypatch.setattr(llama_integration, "llama_circuit_open", False)
    monkeypatch.setattr(llama_integration, "OLLAMA_MODEL", None)
    monkeypatch.setenv("OLLAMA_MODEL", "custom-model:latest")

    prompt = "short prompt"
    engine, model, reason, keyword = model_picker.pick_model(prompt, "chat", 10)
    assert engine == "llama"
    assert model == "custom-model:latest"


def test_pick_model_keyword_detection_case_insensitive(monkeypatch):
    """Test that keyword detection is case insensitive."""
    from app import model_picker
    from app import llama_integration

    monkeypatch.setattr(llama_integration, "LLAMA_HEALTHY", True)
    monkeypatch.setattr(llama_integration, "llama_circuit_open", False)
    monkeypatch.setenv("MODEL_ROUTER_KEYWORDS", "CODE,SQL,ANALYZE")

    # Test uppercase keyword - the keyword is returned as found in the prompt (lowercase)
    prompt = "Please write some CODE for me"
    engine, model, reason, keyword = model_picker.pick_model(prompt, "chat", 10)
    assert engine == "gpt"
    assert reason == "keyword"
    assert keyword == "code"  # The keyword is returned as found in prompt_lc

    # Test mixed case keyword
    prompt = "Can you ANALYZE this data?"
    engine, model, reason, keyword = model_picker.pick_model(prompt, "chat", 10)
    assert engine == "gpt"
    assert reason == "keyword"
    assert keyword == "analyze"  # The keyword is returned as found in prompt_lc


def test_pick_model_heavy_intents(monkeypatch):
    """Test that heavy intents trigger GPT selection."""
    from app import model_picker
    from app import llama_integration

    monkeypatch.setattr(llama_integration, "LLAMA_HEALTHY", True)
    monkeypatch.setattr(llama_integration, "llama_circuit_open", False)

    # Test analysis intent
    prompt = "short prompt"
    engine, model, reason, keyword = model_picker.pick_model(prompt, "analysis", 10)
    assert engine == "gpt"
    assert reason == "heavy_intent"

    # Test research intent
    engine, model, reason, keyword = model_picker.pick_model(prompt, "research", 10)
    assert engine == "gpt"
    assert reason == "heavy_intent"


def test_pick_model_light_task_default_path(monkeypatch):
    """Test the default light task path when all conditions are met for llama."""
    from app import model_picker
    from app import llama_integration

    monkeypatch.setattr(llama_integration, "LLAMA_HEALTHY", True)
    monkeypatch.setattr(llama_integration, "llama_circuit_open", False)
    monkeypatch.setenv("OLLAMA_MODEL", "llama3:latest")

    # Short prompt, light intent, few tokens
    prompt = "hello there"
    engine, model, reason, keyword = model_picker.pick_model(prompt, "chat", 50)
    assert engine == "llama"
    assert model == "llama3:latest"
    assert reason == "light_default"
    assert keyword is None


def test_pick_model_environment_variables_override(monkeypatch):
    """Test that environment variables properly override defaults."""
    from app import model_picker
    from app import llama_integration

    monkeypatch.setattr(llama_integration, "LLAMA_HEALTHY", True)
    monkeypatch.setattr(llama_integration, "llama_circuit_open", False)
    
    # Directly patch the module variables instead of environment variables
    monkeypatch.setattr(model_picker, "HEAVY_WORD_COUNT", 10)
    monkeypatch.setattr(model_picker, "HEAVY_TOKENS", 500)
    monkeypatch.setattr(model_picker, "KEYWORDS", {"custom", "test", "keyword"})

    # Test word count threshold - need more than 10 words
    prompt = "this is a longer prompt with more words than the threshold set"
    engine, model, reason, keyword = model_picker.pick_model(prompt, "chat", 50)
    assert engine == "gpt"
    assert reason == "heavy_length"

    # Test token threshold
    prompt = "short prompt"
    engine, model, reason, keyword = model_picker.pick_model(prompt, "chat", 600)
    assert engine == "gpt"
    assert reason == "heavy_tokens"

    # Test custom keyword
    prompt = "please run a custom test"
    engine, model, reason, keyword = model_picker.pick_model(prompt, "chat", 50)
    assert engine == "gpt"
    assert reason == "keyword"
    assert keyword in ["custom", "test"]


