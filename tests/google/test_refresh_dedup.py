import asyncio
import pytest

from app.integrations.google.refresh import refresh_dedup


class DummyOAuth:
    def __init__(self, resp):
        self._resp = resp

    async def refresh_access_token(self, refresh_token):
        await asyncio.sleep(0.01)
        return self._resp


@pytest.mark.asyncio
async def test_refresh_dedup_concurrency(monkeypatch):
    dummy = {"access_token": "at", "expires_in": 3600}
    monkeypatch.setattr("app.integrations.google.refresh.GoogleOAuth", lambda: DummyOAuth(dummy))

    async def do_refresh(i):
        r = await refresh_dedup("user1", "rt")
        return r

    tasks = [asyncio.create_task(do_refresh(i)) for i in range(5)]
    results = await asyncio.gather(*tasks)
    assert all(r[0] is True for r in results)
    assert all(r[1]["access_token"] == "at" for r in results)


