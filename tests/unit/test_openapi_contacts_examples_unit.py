from fastapi.testclient import TestClient


def _spec():
    from app.main import app
    c = TestClient(app)
    r = c.get("/openapi.json")
    assert r.status_code == 200
    return r.json()


def test_contacts_post_request_example_present():
    spec = _spec()
    op = spec["paths"]["/v1/care/contacts"]["post"]
    rb = op.get("requestBody") or {}
    any_example = any("example" in (content.get("schema") or {}) for content in (rb.get("content") or {}).values())
    assert any_example


def test_contacts_post_response_model_present():
    spec = _spec()
    op = spec["paths"]["/v1/care/contacts"]["post"]
    res = op["responses"]["200"]
    any_schema = any((content.get("schema") or {}) for content in (res.get("content") or {}).values())
    assert any_schema


def test_contacts_patch_response_model_present():
    spec = _spec()
    op = spec["paths"]["/v1/care/contacts/{contact_id}"]["patch"]
    res = op["responses"].get("200") or {}
    any_schema = any((content.get("schema") or {}) for content in (res.get("content") or {}).values())
    assert any_schema


def test_contacts_delete_response_model_present():
    spec = _spec()
    op = spec["paths"]["/v1/care/contacts/{contact_id}"]["delete"]
    res = op["responses"].get("200") or {}
    any_schema = any((content.get("schema") or {}) for content in (res.get("content") or {}).values())
    assert any_schema


def test_contacts_tv_call_response_model_present():
    spec = _spec()
    op = spec["paths"]["/v1/tv/contacts/call"]["post"]
    res = op["responses"].get("200") or {}
    any_schema = any((content.get("schema") or {}) for content in (res.get("content") or {}).values())
    assert any_schema


def test_contacts_request_example_has_quiet_hours_field():
    spec = _spec()
    comp = spec["components"]["schemas"]["ContactBody"]
    example = comp.get("example") or {}
    assert "quiet_hours" in example


def test_contacts_response_component_exists():
    spec = _spec()
    comps = spec["components"]["schemas"]
    assert "ContactCreateResponse" in comps and "ContactUpdateResponse" in comps


