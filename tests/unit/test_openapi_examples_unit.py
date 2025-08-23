from fastapi.testclient import TestClient


def _client():
    from app.main import app

    return TestClient(app)


def _get_openapi():
    c = _client()
    r = c.get("/openapi.json")
    assert r.status_code == 200
    return r.json()


def test_examples_present_for_post_endpoints():
    spec = _get_openapi()
    paths = spec.get("paths", {})
    # representative endpoints across Care, Music, Calendar(Reminders), Admin
    samples = [
        ("/v1/care/alerts", "post"),
        ("/v1/music", "post"),
        ("/v1/vibe", "post"),
        ("/v1/reminders", "post"),
        ("/v1/admin/reload_env", "post"),
        ("/v1/care/contacts", "post"),
    ]
    missing = []
    for path, method in samples:
        op = (paths.get(path) or {}).get(method)
        if not op:
            missing.append((path, method, "no op"))
            continue
        # requestBody example
        rb = op.get("requestBody") or {}
        has_req_example = False
        for content in (rb.get("content") or {}).values():
            schema = content.get("schema") or {}
            if "example" in schema:
                has_req_example = True
                break
        # response example
        res = (op.get("responses") or {}).get("200") or {}
        has_res_model = False
        for content in (res.get("content") or {}).values():
            schema = content.get("schema") or {}
            if schema:
                has_res_model = True
                break
        if not (has_req_example and has_res_model):
            missing.append(
                (
                    path,
                    method,
                    f"req_example={has_req_example} res_model={has_res_model}",
                )
            )
    assert not missing, f"Missing examples/models: {missing}"
