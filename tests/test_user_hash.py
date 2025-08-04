from app.main import _anon_user_id


def test_anon_user_id_length_and_stability():
    token = "Bearer example-token"
    uid = _anon_user_id(token)
    assert len(uid) == 32
    assert _anon_user_id(token) == uid


def test_anon_user_id_without_auth_returns_local():
    assert _anon_user_id(None) == "local"
