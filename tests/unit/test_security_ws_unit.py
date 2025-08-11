import types
import jwt
import pytest


class DummyWS:
    def __init__(self, headers=None, query=None, host="h"):
        self.headers = headers or {}
        self.query_params = query or {}
        self.state = types.SimpleNamespace()
        self.client = types.SimpleNamespace(host=host)


@pytest.mark.asyncio
async def test_verify_ws_header_and_query(monkeypatch):
    from app import security as sec

    monkeypatch.setenv("JWT_SECRET", "secret")

    # via header
    t = jwt.encode({"user_id": "u1"}, "secret", algorithm="HS256")
    ws = DummyWS(headers={"Authorization": f"Bearer {t}"})
    await sec.verify_ws(ws)
    assert getattr(ws.state, "user_id", None) == "u1"

    # via query param
    t2 = jwt.encode({"sub": "u2"}, "secret", algorithm="HS256")
    ws2 = DummyWS(query={"token": t2})
    await sec.verify_ws(ws2)
    assert getattr(ws2.state, "user_id", None) == "u2"

    # invalid token -> remain anon
    ws3 = DummyWS(headers={"Authorization": "Bearer notatoken"})
    await sec.verify_ws(ws3)
    assert not hasattr(ws3.state, "user_id")


@pytest.mark.asyncio
async def test_rate_limit_ws(monkeypatch):
    from app import security as sec

    # generous limits to avoid flake
    monkeypatch.setenv("RATE_LIMIT_PER_MIN", "1000")
    monkeypatch.setenv("RATE_LIMIT_BURST", "3")

    # reset buckets
    sec._ws_requests.clear()
    sec.ws_burst.clear()

    ws = DummyWS()
    ws.state.user_id = "u"
    await sec.rate_limit_ws(ws)
    await sec.rate_limit_ws(ws)
    await sec.rate_limit_ws(ws)


