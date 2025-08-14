import os
from fastapi.testclient import TestClient


def test_csrf_enabled_blocks_without_header(monkeypatch):
    os.environ['CSRF_ENABLED'] = '1'
    from app.main import app
    client = TestClient(app)
    r = client.post('/v1/auth/logout')
    assert r.status_code in (400, 403)


def test_csrf_allows_with_header_and_cookie(monkeypatch):
    os.environ['CSRF_ENABLED'] = '1'
    from app.main import app
    client = TestClient(app)
    # Set csrf cookie and send matching header
    client.cookies.set('csrf_token', 'abc')
    r = client.post('/v1/auth/logout', headers={'X-CSRF-Token': 'abc'})
    assert r.status_code in (200, 401)


