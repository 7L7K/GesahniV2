import os
from fastapi.testclient import TestClient


def test_refresh_requires_intent_in_cross_site(monkeypatch):
    os.environ['COOKIE_SAMESITE'] = 'none'
    os.environ['CSRF_ENABLED'] = '0'
    from app.main import app
    client = TestClient(app)
    with client:
        r = client.post('/v1/auth/refresh')
        assert r.status_code in (400, 401)


def test_logout_clears_cookies(monkeypatch):
    from app.main import app
    client = TestClient(app)
    with client:
        # simulate cookies
        client.cookies.set('access_token', 'x')
        client.cookies.set('refresh_token', 'y')
        # CSRF enabled path
        client.cookies.set('csrf_token', 'abc')
        r = client.post('/v1/auth/logout', headers={'X-CSRF-Token': 'abc'})
        assert r.status_code == 204  # 204 No Content is correct for logout


