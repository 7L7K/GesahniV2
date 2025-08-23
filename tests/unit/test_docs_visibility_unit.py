import importlib
import os

from fastapi.testclient import TestClient


def _reload_app_with_env(env_value: str):
    prev = os.environ.get("ENV")
    os.environ["ENV"] = env_value
    try:
        from app import main as _main

        importlib.reload(_main)
        return _main.app
    finally:
        if prev is None:
            os.environ.pop("ENV", None)
        else:
            os.environ["ENV"] = prev


def _reload_app_with_overrides(overrides: dict[str, str]):
    saved: dict[str, str | None] = {k: os.environ.get(k) for k in overrides}
    os.environ.update({k: v for k, v in overrides.items() if v is not None})
    try:
        from app import main as _main

        importlib.reload(_main)
        return _main.app
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_docs_hidden_in_prod():
    app = _reload_app_with_env("prod")
    c = TestClient(app)
    r = c.get("/docs")
    assert r.status_code == 404
    r = c.get("/redoc")
    assert r.status_code == 404
    r = c.get("/openapi.json")
    assert r.status_code == 404


def test_docs_visible_in_dev_and_persist_auth_and_filter():
    app = _reload_app_with_env("dev")
    c = TestClient(app)
    r = c.get("/docs")
    assert r.status_code == 200
    html = r.text
    assert "persistAuthorization" in html
    assert "docExpansion" in html and "list" in html
    assert "filter" in html
    # openapi.json should exist
    r2 = c.get("/openapi.json")
    assert r2.status_code == 200
    data = r2.json()
    # Title and version present
    assert data.get("info", {}).get("title") == "Granny Mode API"
    assert "version" in data.get("info", {})
    # Servers should be present in dev
    assert isinstance(data.get("servers"), list) and len(data["servers"]) >= 1


def test_openapi_title_and_version_from_app_version_env():
    app = _reload_app_with_overrides({"ENV": "dev", "APP_VERSION": "1.2.3"})
    c = TestClient(app)
    r = c.get("/openapi.json")
    assert r.status_code == 200
    data = r.json()
    assert data.get("info", {}).get("title") == "Granny Mode API"
    assert data.get("info", {}).get("version") == "1.2.3"


def test_openapi_servers_override_env():
    servers = "http://a.local:9000, http://b.local:9001"
    app = _reload_app_with_overrides({"ENV": "dev", "OPENAPI_DEV_SERVERS": servers})
    c = TestClient(app)
    r = c.get("/openapi.json")
    assert r.status_code == 200
    data = r.json()
    urls = [s.get("url") for s in data.get("servers", [])]
    assert urls == ["http://a.local:9000", "http://b.local:9001"]


def test_oauth2_security_scheme_present_with_scopes():
    app = _reload_app_with_env("dev")
    c = TestClient(app)
    r = c.get("/openapi.json")
    assert r.status_code == 200
    data = r.json()
    comps = data.get("components", {}).get("securitySchemes", {})
    assert "OAuth2" in comps
    oauth2 = comps["OAuth2"]
    assert oauth2.get("type") == "oauth2"
    flows = oauth2.get("flows", {})
    assert "password" in flows
    password = flows["password"]
    assert password.get("tokenUrl", "").endswith("/v1/auth/token")
    scopes = password.get("scopes", {})
    # Check a few representative scopes are present
    for scope in ["care:resident", "care:caregiver", "music:control", "admin:write"]:
        assert scope in scopes


def test_docs_hidden_in_staging_env():
    app = _reload_app_with_env("staging")
    c = TestClient(app)
    assert c.get("/docs").status_code == 404
    assert c.get("/openapi.json").status_code == 404
    assert c.get("/redoc").status_code == 404


def test_docs_visible_with_env_case_and_whitespace():
    app = _reload_app_with_env("  DeV  ")
    c = TestClient(app)
    assert c.get("/docs").status_code == 200
    assert c.get("/openapi.json").status_code == 200
    assert c.get("/redoc").status_code == 200


def test_openapi_tags_present():
    app = _reload_app_with_env("dev")
    c = TestClient(app)
    r = c.get("/openapi.json")
    assert r.status_code == 200
    data = r.json()
    tag_names = {t.get("name") for t in data.get("tags", [])}
    # Our curated tags should be present
    expected = {"Care", "Music", "Calendar", "TV", "Admin", "Auth"}
    assert expected.issubset(tag_names)
