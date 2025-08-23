import os
from urllib.parse import urlencode

from fastapi.testclient import TestClient


def _client():
    # Make auth optional and configure admin token for this test session
    os.environ.setdefault("PYTEST_RUNNING", "1")
    os.environ.setdefault("JWT_OPTIONAL_IN_TESTS", "1")
    os.environ.setdefault("ADMIN_TOKEN", "t")
    from app.main import app
    return TestClient(app)


def _openapi():
    c = _client()
    r = c.get("/openapi.json")
    assert r.status_code == 200
    return r.json()


def _resolve_example(schema: dict, components: dict) -> tuple[dict | None, str | None]:
    # Returns (example, ref_name)
    if not schema:
        return None, None
    if "example" in schema:
        return schema.get("example"), None
    ref = schema.get("$ref")
    if ref and ref.startswith("#/components/schemas/"):
        name = ref.split("/")[-1]
        comp = (components.get("schemas") or {}).get(name) or {}
        ex = comp.get("example")
        return ex, name
    return None, None


def test_openapi_contract_models_examples_present():
    spec = _openapi()
    paths = spec.get("paths", {})
    components = spec.get("components", {})
    missing = []
    for path, ops in paths.items():
        if not path.startswith("/v1/"):
            continue
        for method, op in ops.items():
            if method.lower() not in {"post", "put"}:
                continue
            rb = op.get("requestBody") or {}
            content = rb.get("content") or {}
            json_schema = None
            for mt, item in content.items():
                if mt.startswith("application/json"):
                    json_schema = (item.get("schema") or {})
                    break
            # Require example for JSON bodies when present
            if json_schema is not None:
                example, ref_name = _resolve_example(json_schema, components)
                if example is None:
                    missing.append((path, method, "request.example_missing"))
            # Require response model schema for 200
            resp = (op.get("responses") or {}).get("200") or {}
            any_schema = any((c.get("schema") or {}) for c in (resp.get("content") or {}).values())
            if not any_schema:
                missing.append((path, method, "response.schema_missing"))
    assert not missing, f"Missing OpenAPI examples/schemas: {missing}"


def test_openapi_contract_hits_examples():
    spec = _openapi()
    c = _client()
    paths = spec.get("paths", {})
    components = spec.get("components", {})
    blocked_substrings = (
        "/upload",
        "/capture/",
        "/tts/",
        "/ha/webhook",
        "/admin/backup",
        "/admin/vector_store/",  # external deps
        "/sessions/",
        "/transcribe/",
        "/summarize",
    )
    errors: list[tuple[str, str, str]] = []
    for path, ops in paths.items():
        if not path.startswith("/v1/"):
            continue
        if any(x in path for x in blocked_substrings):
            continue
        if "{" in path:
            continue  # skip dynamic path params for smoke
        for method, op in ops.items():
            if method.lower() not in {"post", "put"}:
                continue
            rb = op.get("requestBody") or {}
            content = rb.get("content") or {}
            json_schema = None
            for mt, item in content.items():
                if mt.startswith("application/json"):
                    json_schema = (item.get("schema") or {})
                    break
            if json_schema is None:
                continue
            example, _ = _resolve_example(json_schema, components)
            if example is None:
                continue
            url = path
            params = {}
            if url.startswith("/v1/admin/"):
                params["token"] = os.getenv("ADMIN_TOKEN", "t")
            if params:
                url = f"{url}?{urlencode(params)}"
            resp = c.request(method.upper(), url, json=example)
            if resp.status_code not in (200, 400, 401, 403):
                errors.append((path, method, f"status={resp.status_code}"))
    assert not errors, f"Example POST/PUT calls failed: {errors}"


