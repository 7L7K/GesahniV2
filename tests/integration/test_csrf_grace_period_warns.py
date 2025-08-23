from http import HTTPStatus

from fastapi.testclient import TestClient

from app.main import app


def test_csrf_grace_period_warns(monkeypatch, capsys):
    monkeypatch.setenv("CSRF_ENABLED", "1")
    monkeypatch.setenv("CSRF_LEGACY_GRACE", "1")
    c = TestClient(app)
    c.cookies.set("csrf_token", "tok")
    r = c.post("/v1/profile", headers={"X-CSRF": "tok"}, json={})
    assert r.status_code == HTTPStatus.OK
    out = capsys.readouterr().out
    assert "csrf.legacy_header used" in out
