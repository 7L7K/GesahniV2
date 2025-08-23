def test_get_redaction_map_invalid_json(tmp_path, monkeypatch):
    import importlib

    from app import redaction

    monkeypatch.setenv("REDACTIONS_DIR", str(tmp_path))
    importlib.reload(redaction)

    p = (tmp_path / "k" / "i.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{not json}", encoding="utf-8")

    data = redaction.get_redaction_map("k", "i")
    assert data == {}


