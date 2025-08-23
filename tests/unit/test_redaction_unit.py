

def test_redact_pii_and_store(tmp_path, monkeypatch):
    from app import redaction

    monkeypatch.setenv("REDACTIONS_DIR", str(tmp_path))

    # re-import to apply new base dir
    import importlib
    importlib.reload(redaction)

    text = "Email a@b.com call +1 555-123-4567 and ssn 123-45-6789"
    red, mapping = redaction.redact_pii(text)
    assert "a@b.com" not in red and mapping

    redaction.store_redaction_map("test", "item1", mapping)
    loaded = redaction.get_redaction_map("test", "item1")
    assert loaded == mapping

    again = redaction.redact_and_store("test", "item2", text)
    assert again != text


