from app.api.spotify import _recent_refresh, _token_scope_list


def test_token_scope_list_variants():
    class T:
        pass

    t = T()
    t.scopes = "user-read-email user-read-private"
    assert _token_scope_list(t) == ["user-read-email", "user-read-private"]

    t.scopes = "user-read-email,user-read-private"
    assert set(_token_scope_list(t)) == {"user-read-email", "user-read-private"}

    t.scopes = ["user-read-email", "user-read-private"]
    assert _token_scope_list(t) == ["user-read-email", "user-read-private"]

    t.scopes = None
    assert _token_scope_list(t) == []


def test_recent_refresh_boundaries(monkeypatch):
    now = 1_000_000
    assert _recent_refresh(now - 3599, now=now) is True
    assert _recent_refresh(now - 3600, now=now) is False
