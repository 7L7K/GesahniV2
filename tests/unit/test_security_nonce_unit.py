import pytest
from starlette.requests import Request


@pytest.mark.asyncio
async def test_require_nonce_enforced(monkeypatch):
    import app.security as sec

    monkeypatch.setenv("REQUIRE_NONCE", "1")
    req = Request({"type": "http", "method": "POST", "path": "/", "headers": [(b"x-nonce", b"abc")]})
    await sec.require_nonce(req)
    # reuse should fail
    with pytest.raises(Exception):
        await sec.require_nonce(req)


