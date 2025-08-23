def test_sanitize_and_map_path(tmp_path, monkeypatch):
    import importlib

    from app import redaction

    monkeypatch.setenv("REDACTIONS_DIR", str(tmp_path))
    importlib.reload(redaction)

    s = redaction._sanitize_segment("a b$c")
    assert s == "a_b_c"

    p = redaction._map_path("k@", "i#")
    assert str(p).startswith(str(tmp_path)) and p.name.endswith(".json")


