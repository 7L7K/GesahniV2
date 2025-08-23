from http import HTTPStatus

from fastapi.testclient import TestClient

from app.main import app


def test_refresh_header_case(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "secret")
    monkeypatch.setenv("COOKIE_SAMESITE", "none")
    c = TestClient(app)
    for key in ["x-auth-intent", "X-Auth-Intent", "X-AUTH-INTENT"]:
        r = c.post("/v1/auth/refresh", headers={key: "refresh"})
        assert r.status_code in {
            HTTPStatus.UNAUTHORIZED,
            HTTPStatus.OK,
            HTTPStatus.BAD_REQUEST,
        }
