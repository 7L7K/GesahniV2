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


def test_ws_helper_available_in_dev():
    app = _reload_app_with_env("dev")
    c = TestClient(app)
    r = c.get("/docs/ws")
    assert r.status_code == 200
    assert "WebSocket helper" in r.text


def test_ws_helper_hidden_in_prod():
    app = _reload_app_with_env("prod")
    c = TestClient(app)
    r = c.get("/docs/ws")
    assert r.status_code == 404


def test_ws_helper_contains_inputs_and_buttons():
    app = _reload_app_with_env("dev")
    c = TestClient(app)
    html = c.get("/docs/ws").text
    for needle in [
        "id=\"url\"",
        "id=\"token\"",
        "id=\"resident\"",
        "id=\"topic\"",
        "id=\"btnConnect\"",
        "id=\"btnDisconnect\"",
        "id=\"btnSubscribe\"",
        "id=\"btnPing\"",
        "id=\"events\"",
    ]:
        assert needle in html


def test_ws_helper_default_url_points_to_ws_care():
    app = _reload_app_with_env("dev")
    c = TestClient(app)
    html = c.get("/docs/ws").text
    assert "/v1/ws/care" in html


def test_ws_helper_shows_subscribe_payload_hint():
    app = _reload_app_with_env("dev")
    c = TestClient(app)
    html = c.get("/docs/ws").text
    assert '{\\"action\\":\\"subscribe\\",\\"topic\\":\\"resident:{id}\\"}' in html


def test_ws_helper_title_and_styles_present():
    app = _reload_app_with_env("dev")
    c = TestClient(app)
    html = c.get("/docs/ws").text
    assert "<title>WS Helper • Granny Mode API</title>" in html
    assert "#events" in html


def test_ws_helper_includes_token_query_logic():
    app = _reload_app_with_env("dev")
    c = TestClient(app)
    html = c.get("/docs/ws").text
    # Ensure we append token query param when present
    assert "token=' + encodeURIComponent(t)" in html

