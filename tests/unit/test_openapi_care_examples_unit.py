from fastapi.testclient import TestClient


def _spec():
    from app.main import app

    return TestClient(app).get("/openapi.json").json()


def test_care_alerts_post_has_example_and_response_model():
    spec = _spec()
    op = spec["paths"]["/v1/care/alerts"]["post"]
    rb = op.get("requestBody") or {}
    any_example = any(
        "example" in (c.get("schema") or {}) for c in (rb.get("content") or {}).values()
    )
    res = op["responses"]["200"]
    any_schema = any(
        (c.get("schema") or {}) for c in (res.get("content") or {}).values()
    )
    assert any_example and any_schema


def test_care_ack_post_response_model_present():
    spec = _spec()
    op = spec["paths"]["/v1/care/alerts/{alert_id}/ack"]["post"]
    res = op["responses"]["200"]
    any_schema = any(
        (c.get("schema") or {}) for c in (res.get("content") or {}).values()
    )
    assert any_schema


def test_care_resolve_post_response_model_present():
    spec = _spec()
    op = spec["paths"]["/v1/care/alerts/{alert_id}/resolve"]["post"]
    res = op["responses"]["200"]
    any_schema = any(
        (c.get("schema") or {}) for c in (res.get("content") or {}).values()
    )
    assert any_schema


def test_care_heartbeat_request_example_present():
    spec = _spec()
    comp = spec["components"]["schemas"]["Heartbeat"]
    assert "example" in comp


def test_care_sessions_post_request_example_present():
    spec = _spec()
    comp = spec["components"]["schemas"]["SessionBody"]
    assert "example" in comp


def test_care_sessions_post_response_model_present():
    spec = _spec()
    op = spec["paths"]["/v1/care/sessions"]["post"]
    res = op["responses"]["200"]
    any_schema = any(
        (c.get("schema") or {}) for c in (res.get("content") or {}).values()
    )
    assert any_schema


def test_care_components_alertrecord_exists():
    spec = _spec()
    schemas = spec["components"]["schemas"]
    assert "AlertRecord" in schemas
