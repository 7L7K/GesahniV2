from app.token_utils import count_tokens


def test_count_tokens_handles_spaces_and_nospaces():
    assert count_tokens("") == 0
    # with spaces counts at least words
    assert count_tokens("a b c d") >= 4
    # long nospace string approximates 4 chars/token
    s = "x" * 40
    assert 9 <= count_tokens(s) <= 11
