def test_sanitize_and_map_path(tmp_path, monkeypatch):
    from app import redaction
    import importlib

    monkeypatch.setenv("REDACTIONS_DIR", str(tmp_path))
    importlib.reload(redaction)

    s = redaction._sanitize_segment("a b$c")
    assert s == "a_b_c"

    p = redaction._map_path("k@", "i#")
    assert str(p).startswith(str(tmp_path)) and p.name.endswith(".json")


