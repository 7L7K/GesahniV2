from fastapi.testclient import TestClient


def _spec():
    from app.main import app

    return TestClient(app).get("/openapi.json").json()


def test_tv_photos_favorite_response_model_present():
    spec = _spec()
    op = spec["paths"]["/v1/tv/photos/favorite"]["post"]
    res = op["responses"]["200"]
    any_schema = any(
        (c.get("schema") or {}) for c in (res.get("content") or {}).values()
    )
    assert any_schema


def test_tv_alert_response_model_present():
    spec = _spec()
    op = spec["paths"]["/v1/tv/alert"]["post"]
    res = op["responses"]["200"]
    any_schema = any(
        (c.get("schema") or {}) for c in (res.get("content") or {}).values()
    )
    assert any_schema


def test_tv_music_play_response_model_present():
    spec = _spec()
    op = spec["paths"]["/v1/tv/music/play"]["post"]
    res = op["responses"]["200"]
    any_schema = any(
        (c.get("schema") or {}) for c in (res.get("content") or {}).values()
    )
    assert any_schema


def test_tv_prefs_response_model_present():
    spec = _spec()
    op = spec["paths"]["/v1/tv/prefs"]["post"]
    res = op["responses"]["200"]
    any_schema = any(
        (c.get("schema") or {}) for c in (res.get("content") or {}).values()
    )
    assert any_schema


def test_tv_stage2_response_model_present():
    spec = _spec()
    op = spec["paths"]["/v1/tv/stage2"]["post"]
    res = op["responses"]["200"]
    any_schema = any(
        (c.get("schema") or {}) for c in (res.get("content") or {}).values()
    )
    assert any_schema


def test_tv_tags_present():
    spec = _spec()
    assert any(x.get("name") == "TV" for x in spec.get("tags", []))


def test_tv_paths_nonempty():
    spec = _spec()
    assert any(p.startswith("/v1/tv/") for p in spec["paths"].keys())
