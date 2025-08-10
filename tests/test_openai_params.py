import os
from app.model_params import for_openai, merge_params


def test_openai_omits_max_tokens_by_default(monkeypatch):
    monkeypatch.delenv('GEN_MAX_TOKENS', raising=False)
    mp = for_openai({})
    assert 'max_tokens' not in mp


def test_openai_passes_max_completion_tokens(monkeypatch):
    monkeypatch.delenv('GEN_MAX_TOKENS', raising=False)
    params = merge_params({'max_completion_tokens': 123})
    mapped = for_openai(params)
    assert mapped.get('max_completion_tokens') == 123
    assert 'max_tokens' not in mapped


