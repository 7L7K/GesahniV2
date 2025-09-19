import pytest
from starlette.responses import Response
from types import SimpleNamespace

from app.web import cookies as cookies_mod


class _StubMetric:
    def __init__(self) -> None:
        self.called = False
        self.labels_kwargs = None

    def labels(self, **kwargs):
        self.labels_kwargs = kwargs
        return self

    def inc(self):
        self.called = True


def _make_request(cookie_map: dict[str, str]):
    return SimpleNamespace(cookies=cookie_map, state=SimpleNamespace())


def test_pick_cookie_prefers_canonical_and_schedules_cleanup(monkeypatch):
    metric = _StubMetric()
    monkeypatch.setattr(cookies_mod, "COOKIE_CONFLICT", metric)

    request = _make_request({
        "__Host-GSNH_AT": "host-token",
        "access_token": "legacy-token",
    })

    name, value = cookies_mod.pick_cookie(request, cookies_mod.AT_ORDER)

    assert name == "__Host-GSNH_AT"
    assert value == "host-token"

    cleanup = getattr(request.state, "_legacy_cookie_cleanup")
    assert "access_token" in cleanup.get("access_token", set())
    assert metric.called
    assert metric.labels_kwargs == {"cookie_type": "access_token"}


def test_append_cookie_emits_legacy_clear_on_cleanup():
    request = SimpleNamespace(
        state=SimpleNamespace(_legacy_cookie_cleanup={"access_token": {"access_token"}})
    )
    response = Response()

    cookies_mod._append_cookie(
        response,
        key="GSNH_AT",
        value="new-access",
        max_age=60,
        http_only=True,
        same_site="Lax",
        domain=None,
        path="/",
        secure=True,
        request=request,
    )

    headers = response.headers.getlist("set-cookie")
    assert any("GSNH_AT=new-access" in header for header in headers)
    assert any("access_token=" in header and "Max-Age=0" in header for header in headers)


def test_append_cookie_forces_secure_when_samesite_none():
    response = Response()

    cookies_mod._append_cookie(
        response,
        key="GSNH_AT",
        value="value",
        max_age=30,
        http_only=True,
        same_site="None",
        domain=None,
        path="/",
        secure=False,
    )

    header = response.headers.get("set-cookie")
    assert header is not None
    assert "Secure" in header


def test_host_cookie_requires_root_path_and_no_domain():
    response = Response()

    with pytest.raises(AssertionError):
        cookies_mod._append_cookie(
            response,
            key="__Host-GSNH_AT",
            value="value",
            max_age=60,
            http_only=True,
            same_site="Lax",
            domain="example.com",
            path="/",
            secure=True,
        )
