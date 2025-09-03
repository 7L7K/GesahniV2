import pytest
from fastapi import Response


def test_set_named_cookie_enforces_samesite_none_secure(monkeypatch):
    # Arrange: force config to insecure by default to test enforcement
    def fake_cfg(_request):
        return {
            "secure": False,
            "samesite": "lax",
            "httponly": True,
            "path": "/",
            "domain": None,
        }

    from app import cookie_config

    monkeypatch.setattr(cookie_config, "get_cookie_config", fake_cfg)

    from app.cookies import set_named_cookie

    class DummyReq:
        # minimal placeholder; cookie_config was monkeypatched above
        pass

    req = DummyReq()
    resp = Response()

    # Act: request SameSite=None without secure=True; helper should auto-enable Secure
    set_named_cookie(
        resp,
        name="tmp",
        value="v",
        ttl=60,
        request=req,  # cookie_config is monkeypatched, so no attributes needed
        samesite="none",
        secure=False,  # will be overridden by helper due to None+Secure policy
    )

    # Assert: header contains SameSite=None and Secure
    cookie_headers = resp.headers.getlist("set-cookie")
    assert cookie_headers, "expected a Set-Cookie header"
    h = cookie_headers[-1]
    assert "SameSite=None" in h
    assert "Secure" in h
