from fastapi.testclient import TestClient

from app.main import app


def test_admin_tv_config_examples_and_scopes_present_in_docs():
    c = TestClient(app)
    schema = c.get("/openapi.json").json()
    paths = schema.get("paths", {})
    assert "/v1/admin/tv/config" in paths

    # GET example
    get_op = paths["/v1/admin/tv/config"]["get"]
    ex_get = get_op["responses"]["200"]["content"]["application/json"].get("example")
    assert isinstance(ex_get, dict) and "config" in ex_get

    # PUT example
    put_op = paths["/v1/admin/tv/config"]["put"]
    ex_put = put_op["responses"]["200"]["content"]["application/json"].get("example")
    assert isinstance(ex_put, dict) and "config" in ex_put

    # OAuth2 locks present (from global admin router docs binding)
    assert any("OAuth2" in d for d in get_op.get("security", []))
    assert any("OAuth2" in d for d in put_op.get("security", []))


