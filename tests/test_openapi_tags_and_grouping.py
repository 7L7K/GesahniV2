import pytest


def _openapi():
    # Import lazily to avoid side effects during collection
    from app.main import app

    return app.openapi()


def _find_op(openapi: dict, path: str, method: str) -> dict:
    ops = openapi.get("paths", {}).get(path, {})
    op = ops.get(method.lower()) or ops.get(method.upper())
    assert isinstance(op, dict), f"operation not found: {method} {path}"
    return op


def _schema(openapi: dict, ref: str) -> dict:
    assert ref.startswith("#/components/schemas/"), f"unexpected $ref: {ref}"
    name = ref.split("/")[-1]
    schema = openapi.get("components", {}).get("schemas", {}).get(name)
    assert isinstance(schema, dict), f"schema not found: {name}"
    return schema


def test_openapi_has_exactly_six_tag_groups_in_order():
    o = _openapi()
    names = [t.get("name") for t in o.get("tags", [])]
    assert names == [
        "Care",
        "Music",
        "Calendar",
        "TV",
        "Admin",
        "Auth",
    ]


def test_no_extra_operation_tags():
    o = _openapi()
    allowed = {"Care", "Music", "Calendar", "TV", "Admin", "Auth"}
    seen = set()
    for _path, methods in o.get("paths", {}).items():
        for _m, op in methods.items():
            if isinstance(op, dict):
                for t in (op.get("tags") or []):
                    seen.add(t)
    assert seen.issubset(allowed), f"unexpected tags present: {sorted(seen - allowed)}"
    # ensure each group appears at least once
    for g in allowed:
        assert g in seen, f"group missing: {g}"


@pytest.mark.parametrize(
    "path,method,expected_tag",
    [
        ("/v1/admin/metrics", "get", "Admin"),
        ("/v1/music", "post", "Music"),
        ("/v1/tts/speak", "post", "Music"),
        ("/v1/calendar/next", "get", "Calendar"),
        ("/v1/tv/photos", "get", "TV"),
        ("/v1/care/contacts", "get", "Care"),
        ("/v1/login", "post", "Auth"),
    ],
)
def test_specific_endpoints_are_grouped_by_expected_tag(path: str, method: str, expected_tag: str):
    o = _openapi()
    op = _find_op(o, path, method)
    assert expected_tag in (op.get("tags") or []), f"{path} not tagged as {expected_tag}"


def test_healthz_is_admin_tag():
    o = _openapi()
    op = _find_op(o, "/healthz", "get")
    assert op.get("tags") == ["Admin"]


@pytest.mark.parametrize(
    "path,method,req_schema_name,res_schema_name",
    [
        ("/v1/tts/speak", "post", "TTSRequest", "TTSAck"),
        ("/v1/music", "post", "MusicCommand", "OkResponse"),
        ("/v1/vibe", "post", "VibeBody", "VibeResponse"),
        ("/v1/profile", "post", "UserProfile", "ProfileOk"),
        ("/v1/reminders", "post", "ReminderCreate", "OkResponse"),
        ("/v1/care/contacts", "post", "ContactBody", "ContactCreateResponse"),
        ("/v1/care/alerts", "post", "AlertCreate", "AlertRecord"),
    ],
)
def test_examples_present_on_request_and_response_models(path, method, req_schema_name, res_schema_name):
    o = _openapi()
    op = _find_op(o, path, method)
    # Request schema example
    rb = op.get("requestBody", {})
    assert isinstance(rb, dict) and rb, f"missing requestBody for {path}"
    content = rb.get("content", {}).get("application/json", {})
    sch = (content.get("schema") or {})
    ref = sch.get("$ref")
    assert ref and ref.endswith("/" + req_schema_name), f"unexpected request schema for {path}: {ref}"
    req_schema = _schema(o, ref)
    assert "example" in req_schema, f"missing example on {req_schema_name}"
    # Response schema example
    res = (op.get("responses") or {}).get("200") or {}
    content = (res.get("content") or {}).get("application/json") or {}
    sch = (content.get("schema") or {})
    ref = sch.get("$ref")
    assert ref and ref.endswith("/" + res_schema_name), f"unexpected 200 model for {path}: {ref}"
    res_schema = _schema(o, ref)
    assert "example" in res_schema, f"missing example on {res_schema_name}"


def test_auth_token_endpoint_present_and_tagged_auth():
    o = _openapi()
    op = _find_op(o, "/v1/auth/token", "post")
    assert "Auth" in (op.get("tags") or [])


