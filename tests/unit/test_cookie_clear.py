from fastapi import Response

from app.cookies import clear_csrf_cookie


def test_clear_csrf_cookie_sets_max_age_zero_and_same_path():
    r = Response()
    # simulate request not required for clear helper
    clear_csrf_cookie(r, request=None)
    sc = r.headers.get("set-cookie", "")
    assert "csrf_token=" in sc
    assert "Max-Age=0" in sc or "max-age=0" in sc
    assert "Path=/" in sc


