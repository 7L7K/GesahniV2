from app.model_router import route_text


def test_branch_short_default():
    d = route_text(user_prompt="hi", prompt_tokens=3, retrieved_docs=[])
    assert d.model == "gpt-5-nano"
    assert d.reason == "default"


def test_branch_long_context_docs():
    # Ensure approx token count > RAG_LONG_CONTEXT_THRESHOLD (~6000)
    docs = ["x" * 3000] * 10  # ≈ (3000/4)*10 = 7500 tokens
    d = route_text(user_prompt="q", retrieved_docs=docs)
    assert d.reason in {"long-context", "long-prompt"}


def test_branch_attachments():
    d = route_text(user_prompt="see file", attachments_count=2)
    assert d.reason == "attachments"


def test_branch_ops_simple():
    d = route_text(user_prompt="ops", intent="ops", ops_files_count=1)
    assert d.reason == "ops-simple"
    assert d.model == "gpt-5-nano"


def test_branch_ops_complex():
    d = route_text(user_prompt="ops", intent="ops", ops_files_count=5)
    assert d.reason == "ops-complex"
    assert d.model == "gpt-4.1-nano"


def test_branch_long_prompt():
    d = route_text(user_prompt="x" * 1200)  # ~300 approx tokens in fallback
    assert d.reason in {"long-prompt", "long-context"}
