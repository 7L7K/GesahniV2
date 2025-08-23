import importlib

from starlette.testclient import TestClient


def test_csrf_cookie_flags():
    if "app.main" in importlib.sys.modules:
        del importlib.sys.modules["app.main"]
    from app.main import app
    c = TestClient(app)
    r = c.get("/v1/csrf")
    assert r.status_code == 200
    ck = r.headers.get("set-cookie","")
    assert "Path=/" in ck
    assert "HttpOnly" not in ck  # double-submit pattern
