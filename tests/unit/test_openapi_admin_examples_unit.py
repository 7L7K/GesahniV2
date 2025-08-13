from fastapi.testclient import TestClient


def _spec():
    from app.main import app
    return TestClient(app).get("/openapi.json").json()


def test_admin_reload_env_response_model_present():
    spec = _spec()
    op = spec["paths"]["/v1/admin/reload_env"]["post"]
    res = op["responses"]["200"]
    any_schema = any((c.get("schema") or {}) for c in (res.get("content") or {}).values())
    assert any_schema


def test_admin_bootstrap_response_model_present():
    spec = _spec()
    op = spec["paths"]["/v1/admin/vector_store/bootstrap"]["post"]
    res = op["responses"]["200"]
    any_schema = any((c.get("schema") or {}) for c in (res.get("content") or {}).values())
    assert any_schema


def test_admin_migrate_response_model_present():
    spec = _spec()
    op = spec["paths"]["/v1/admin/vector_store/migrate"]["post"]
    res = op["responses"]["200"]
    any_schema = any((c.get("schema") or {}) for c in (res.get("content") or {}).values())
    assert any_schema


def test_admin_flags_response_model_present():
    spec = _spec()
    op = spec["paths"]["/v1/admin/flags"]["post"]
    res = op["responses"]["200"]
    any_schema = any((c.get("schema") or {}) for c in (res.get("content") or {}).values())
    assert any_schema


def test_admin_components_response_schemas_exist():
    spec = _spec()
    schemas = spec["components"]["schemas"]
    for k in ("AdminOkResponse", "AdminBootstrapResponse", "AdminStartedResponse", "AdminFlagsResponse"):
        assert k in schemas


def test_admin_tags_present():
    spec = _spec()
    assert any(x.get("name") == "Admin" for x in spec.get("tags", []))


def test_admin_paths_nonempty():
    spec = _spec()
    assert any(p.startswith("/v1/admin/") for p in spec["paths"].keys())


