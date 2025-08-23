import concurrent.futures as cf
from http import HTTPStatus

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.mark.contract
def test_refresh_concurrent_two_calls(monkeypatch):
    monkeypatch.setenv('CSRF_ENABLED', '0')
    c = TestClient(app)
    with c:
        c.post('/v1/register', json={'username': 'rc_user', 'password': 'secret123'})
        c.post('/v1/login', json={'username': 'rc_user', 'password': 'secret123'})
        ref = c.cookies.get('refresh_token')
        assert ref, 'missing refresh_token cookie after login'
        def call():
            cc = TestClient(app)
            return cc.post('/v1/auth/refresh', json={'refresh_token': ref}).status_code
        with cf.ThreadPoolExecutor(max_workers=2) as ex:
            a = ex.submit(call); b = ex.submit(call)
            r = sorted([a.result(), b.result()])
        assert r[0] == HTTPStatus.OK and r[1] == HTTPStatus.UNAUTHORIZED

 
