import os
from fastapi.testclient import TestClient


def _auth():
    import jwt as _jwt
    token = _jwt.encode({"user_id": "u_test"}, os.getenv("JWT_SECRET", "secret"), algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


def test_recommendations_cache_respects_limit(monkeypatch):
    from app.main import app
    import app.api.music as music
    from app.models.music_state import load_state, save_state

    monkeypatch.setenv("JWT_SECRET", "secret")
    monkeypatch.setenv("JWT_OPTIONAL_IN_TESTS", "1")
    monkeypatch.setattr(music, "PROVIDER_SPOTIFY", True)

    st = load_state("u_test")
    st.last_recommendations = None
    st.recs_cached_at = None
    save_state("u_test", st)

    many = [
        {"id": f"t{i}", "name": "", "artists": [], "album": {"images": []}, "explicit": False}
        for i in range(25)
    ]
    monkeypatch.setattr(music, "_provider_recommendations", lambda uid, seed_tracks=None, vibe=None, limit=10: many)
    c = TestClient(app)
    # First fills cache
    out1 = c.get("/v1/recommendations?limit=10", headers=_auth()).json()
    assert len(out1["recommendations"]) == 10
    # Now request smaller limit and ensure cache truncation
    out2 = c.get("/v1/recommendations?limit=3", headers=_auth()).json()
    assert len(out2["recommendations"]) == 3


