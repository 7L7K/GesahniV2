from fastapi.testclient import TestClient


def _spec():
    from app.main import app

    return TestClient(app).get("/openapi.json").json()


def test_music_post_request_example_present():
    spec = _spec()
    comp = spec["components"]["schemas"]["MusicCommand"]
    assert "example" in comp


def test_music_post_response_model_present():
    spec = _spec()
    op = spec["paths"]["/v1/music"]["post"]
    res = op["responses"]["200"]
    any_schema = any(
        (c.get("schema") or {}) for c in (res.get("content") or {}).values()
    )
    assert any_schema


def test_vibe_post_request_example_present():
    spec = _spec()
    comp = spec["components"]["schemas"]["VibeBody"]
    assert "example" in comp


def test_vibe_post_response_model_present():
    spec = _spec()
    op = spec["paths"]["/v1/vibe"]["post"]
    res = op["responses"]["200"]
    any_schema = any(
        (c.get("schema") or {}) for c in (res.get("content") or {}).values()
    )
    assert any_schema


def test_restore_post_response_model_present():
    spec = _spec()
    op = spec["paths"]["/v1/music/restore"]["post"]
    res = op["responses"]["200"]
    any_schema = any(
        (c.get("schema") or {}) for c in (res.get("content") or {}).values()
    )
    assert any_schema


def test_device_post_request_example_present():
    spec = _spec()
    comp = spec["components"]["schemas"]["DeviceBody"]
    assert "example" in comp


def test_device_post_response_model_present():
    spec = _spec()
    op = spec["paths"]["/v1/music/device"]["post"]
    res = op["responses"]["200"]
    any_schema = any(
        (c.get("schema") or {}) for c in (res.get("content") or {}).values()
    )
    assert any_schema
