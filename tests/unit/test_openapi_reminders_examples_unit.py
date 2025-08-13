from fastapi.testclient import TestClient


def _spec():
    from app.main import app
    return TestClient(app).get("/openapi.json").json()


def test_reminders_post_request_example_present():
    spec = _spec()
    comp = spec["components"]["schemas"]["ReminderCreate"]
    assert "example" in comp


def test_reminders_post_response_model_present():
    spec = _spec()
    op = spec["paths"]["/v1/reminders"]["post"]
    res = op["responses"]["200"]
    any_schema = any((c.get("schema") or {}) for c in (res.get("content") or {}).values())
    assert any_schema


def test_reminders_accepts_query_or_json_docstring():
    spec = _spec()
    op = spec["paths"]["/v1/reminders"]["post"]
    # requestBody exists
    assert "requestBody" in op
    # also parameters may include query, but not strictly required here
    assert isinstance(op.get("responses"), dict)


def test_reminders_components_okresponse_exists():
    spec = _spec()
    assert "OkResponse" in spec["components"]["schemas"]


def test_reminders_get_exists():
    spec = _spec()
    assert "/v1/reminders" in spec["paths"]
    assert "get" in spec["paths"]["/v1/reminders"]


def test_reminders_delete_exists():
    spec = _spec()
    assert "delete" in spec["paths"]["/v1/reminders"]


