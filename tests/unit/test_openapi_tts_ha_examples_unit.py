from fastapi.testclient import TestClient


def _spec():
    from app.main import app

    return TestClient(app).get("/openapi.json").json()


def test_tts_request_example_present():
    spec = _spec()
    comp = spec["components"]["schemas"]["TTSRequest"]
    assert "example" in comp


def test_tts_post_response_model_present():
    spec = _spec()
    op = spec["paths"]["/v1/tts/speak"]["post"]
    res = op["responses"]["200"]
    any_schema = any(
        (c.get("schema") or {}) for c in (res.get("content") or {}).values()
    )
    assert any_schema


def test_ha_service_post_response_model_present():
    spec = _spec()
    op = spec["paths"]["/v1/ha/service"]["post"]
    res = op["responses"]["200"]
    any_schema = any(
        (c.get("schema") or {}) for c in (res.get("content") or {}).values()
    )
    assert any_schema


def test_ha_webhook_post_response_model_present():
    spec = _spec()
    op = spec["paths"]["/v1/ha/webhook"]["post"]
    res = op["responses"]["200"]
    any_schema = any(
        (c.get("schema") or {}) for c in (res.get("content") or {}).values()
    )
    assert any_schema


def test_core_ask_request_example_present():
    spec = _spec()
    comp = spec["components"]["schemas"]["AskRequest"]
    assert "example" in comp


def test_components_ok_and_ack_exist():
    spec = _spec()
    schemas = spec["components"]["schemas"]
    assert "TTSAck" in schemas and "ServiceAck" in schemas


def test_paths_include_tts_and_ha():
    spec = _spec()
    p = spec["paths"].keys()
    assert "/v1/tts/speak" in p and "/v1/ha/service" in p and "/v1/ha/webhook" in p
