import pytest
from fastapi import FastAPI

from app.main import create_app


@pytest.fixture(scope="module")
def app() -> FastAPI:
    return create_app()


def test_expected_routes_present(app: FastAPI):
    expected = [
        ("GET", "/v1/whoami"),
        ("GET", "/v1/spotify/status"),
        ("GET", "/v1/google/status"),
        ("GET", "/v1/list"),
        ("GET", "/v1/next"),
        ("GET", "/v1/today"),
        ("GET", "/v1/device_status"),
        ("GET", "/v1/music"),
        ("GET", "/v1/music/devices"),
        ("PUT", "/v1/music/device"),
        ("POST", "/v1/transcribe/{job_id}"),
        ("POST", "/v1/tts/speak"),
        ("POST", "/v1/admin/reload_env"),
        ("POST", "/v1/admin/self_review"),
        ("POST", "/v1/admin/vector_store/bootstrap"),
    ]

    # Collect available (METHOD, PATH) pairs from the app router, skipping mounts
    available = set()
    for r in app.router.routes:
        if not hasattr(r, "methods") or not hasattr(r, "path"):
            continue
        for m in r.methods or []:
            available.add((m.upper(), r.path))

    for method, path in expected:
        assert (method, path) in available, f"Missing route {method} {path}"
