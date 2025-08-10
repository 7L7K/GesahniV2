from app.router import _needs_rag


def test_needs_rag_positive_cases():
    assert _needs_rag("What happened in Detroit in 1968?")
    assert _needs_rag("Could you tell me what did I watch yesterday?")


def test_needs_rag_negative_case():
    assert not _needs_rag("hello there")
