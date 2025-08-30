from http import HTTPStatus

from fastapi.testclient import TestClient

from app.main import app
from app.sessions_store import sessions_store
from tests.util_tokens import mint_jwt_token


def _auth_headers():
    tok = mint_jwt_token(sub="tester", secret="secret")
    return {"Authorization": f"Bearer {tok}"}


def test_sessions_paginated(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "secret")
    c = TestClient(app)

    # Create many sessions for the tester
    async def _seed():
        for i in range(55):
            await sessions_store.create_session("tester")

    import asyncio

    asyncio.get_event_loop().run_until_complete(_seed())

    r1 = c.get("/v1/sessions/paginated", headers=_auth_headers(), params={"limit": 50})
    assert r1.status_code == HTTPStatus.OK
    b1 = r1.json()
    assert isinstance(b1, dict)
    assert "items" in b1 and isinstance(b1["items"], list)
    assert len(b1["items"]) <= 50
    # If more available, next_cursor should be present
    if len(b1["items"]) == 50:
        assert b1.get("next_cursor") is not None
        r2 = c.get(
            "/v1/sessions/paginated",
            headers=_auth_headers(),
            params={"cursor": b1["next_cursor"]},
        )
        assert r2.status_code == HTTPStatus.OK
        b2 = r2.json()
        assert isinstance(b2.get("items"), list)
        # Combined should reach total
        assert len(b1["items"]) + len(b2["items"]) >= 55
