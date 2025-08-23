import types


def test_current_key_variants():
    from app.security import _current_key

    assert _current_key(None) == "anon"

    req = types.SimpleNamespace(
        state=types.SimpleNamespace(user_id=None, jwt_payload=None),
        headers={"X-Forwarded-For": "1.2.3.4, 5.6.7.8"},
        client=types.SimpleNamespace(host="h"),
    )
    assert _current_key(req).startswith("1.2.3.4")
