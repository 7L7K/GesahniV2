def test_env_list_parsing(monkeypatch):
    from app import model_params as mp

    monkeypatch.setenv("GEN_STOP", "a,b, c\n d")
    out = mp.base_defaults()
    assert out["stop"] == ["a", "b", "c", "d"]


