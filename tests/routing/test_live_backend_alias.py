from app.routers import normalize_backend_name


def test_normalize_live_prefers_openai(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.delenv("OLLAMA_URL", raising=False)
    monkeypatch.delenv("LLAMA_URL", raising=False)

    assert normalize_backend_name("live") == "openai"


def test_normalize_live_uses_llama_when_openai_missing(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OLLAMA_URL", "http://localhost:11434")
    monkeypatch.delenv("LLAMA_URL", raising=False)

    assert normalize_backend_name("live") == "llama"


def test_normalize_live_falls_back_to_dryrun(monkeypatch):
    for var in ("OPENAI_API_KEY", "OLLAMA_URL", "LLAMA_URL"):
        monkeypatch.delenv(var, raising=False)

    assert normalize_backend_name("live") == "dryrun"


def test_normalize_passthrough_non_live(monkeypatch):
    # Test that non-live names pass through unchanged
    assert normalize_backend_name("openai") == "openai"
    assert normalize_backend_name("llama") == "llama"
    assert normalize_backend_name("dryrun") == "dryrun"


def test_normalize_live_with_both_available(monkeypatch):
    # When both are available, should prefer OpenAI
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OLLAMA_URL", "http://localhost:11434")

    assert normalize_backend_name("live") == "openai"
