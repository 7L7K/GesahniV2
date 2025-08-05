import types

from app import token_utils


def test_count_tokens_uses_tiktoken(monkeypatch):
    fake_encoding = types.SimpleNamespace(encode=lambda text: list(text))
    monkeypatch.setattr(token_utils, "_ENCODING", fake_encoding)
    assert token_utils.count_tokens("hi there") == len("hi there")


def test_count_tokens_fallback(monkeypatch):
    monkeypatch.setattr(token_utils, "_ENCODING", None)
    assert token_utils.count_tokens("hi there") == 2
