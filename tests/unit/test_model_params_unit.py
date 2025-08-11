def test_merge_and_maps(monkeypatch):
    from app import model_params as mp

    monkeypatch.setenv("GEN_TEMPERATURE", "0.2")
    monkeypatch.setenv("GEN_TOP_P", "0.8")
    monkeypatch.delenv("GEN_MAX_TOKENS", raising=False)
    monkeypatch.setenv("GEN_MAX_COMPLETION_TOKENS", "256")

    base = mp.base_defaults()
    assert base["temperature"] == 0.2
    assert base["top_p"] == 0.8
    assert base["max_completion_tokens"] == 256

    merged = mp.merge_params({"stop": "END", "foo": 1})
    assert merged["stop"] == ["END"] and merged["foo"] == 1

    openai_args = mp.for_openai({"max_tokens": 128})
    assert "max_tokens" not in openai_args
    assert openai_args["max_completion_tokens"] in (256, 128)

    ollama_args = mp.for_ollama({"max_tokens": 99, "foo": 2})
    assert ollama_args["num_predict"] == 99 and ollama_args["foo"] == 2


