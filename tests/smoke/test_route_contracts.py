import pytest
from starlette.testclient import TestClient

from app.main import create_app

CASES = [
    ("GET", "/v1/whoami", {401, 200}),  # some suites allow 200 for logged-in cases
    ("GET", "/v1/spotify/status", {200}),
    ("GET", "/v1/google/status", {200}),
    ("GET", "/v1/calendar/list", {200}),
    ("GET", "/v1/calendar/next", {200}),
    ("GET", "/v1/calendar/today", {200}),
    ("GET", "/v1/care/device_status", {200}),
    ("GET", "/v1/music", {200}),
    ("GET", "/v1/music/devices", {200}),
    ("PUT", "/v1/music/device", {200, 400}),
    ("POST", "/v1/transcribe/abc", {202}),
    ("POST", "/v1/tts/speak", {202, 400}),
    (
        "POST",
        "/v1/admin/reload_env",
        {200, 403},
    ),  # CI envs sometimes wrap admin behind auth
    ("POST", "/v1/admin/self_review", {501, 403}),
    ("POST", "/v1/admin/vector_store/bootstrap", {202, 403}),
]


@pytest.mark.parametrize("method,path,allowed", CASES)
def test_contract(method, path, allowed):
    app = create_app()
    with TestClient(app) as c:
        r = c.request(method, path, json={"text": "hi", "device_id": "x"})
        assert (
            r.status_code in allowed
        ), f"{method} {path} -> {r.status_code} not in {allowed}"
        # Ensure JSON body and either a detail or a success code
        assert isinstance(r.json(), dict)
        assert "detail" in r.json() or r.status_code in (200, 202)
