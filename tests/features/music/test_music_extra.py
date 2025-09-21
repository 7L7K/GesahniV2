import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Stable test env
os.environ.setdefault("VECTOR_STORE", "memory")
os.environ.setdefault("GSNH_ENABLE_SPOTIFY", "0")
os.environ.setdefault("GSNH_ENABLE_MUSIC", "1")
os.environ.setdefault("MUSIC_FALLBACK_RADIO", "false")
os.environ.setdefault("JWT_SECRET", "secret")
os.environ.setdefault("REQUIRE_JWT", "0")
os.environ.setdefault("JWT_OPTIONAL_IN_TESTS", "1")

from fastapi.testclient import TestClient

from app.main import app
from app.models.music_state import load_state, save_state


def _client():
    return TestClient(app)


def _auth():
    import jwt as _jwt

    token = _jwt.encode(
        {"user_id": "u_test"}, os.getenv("JWT_SECRET", "secret"), algorithm="HS256"
    )
    return {"Authorization": f"Bearer {token}"}


def test_state_spotify_provider_and_track_mapping(monkeypatch):
    import app.api.music as music

    monkeypatch.setattr(music, "PROVIDER_SPOTIFY", True)
    monkeypatch.setattr(
        music,
        "_provider_state",
        lambda uid: {
            "is_playing": True,
            "progress_ms": 12345,
            "item": {
                "id": "trkA",
                "name": "Alpha",
                "duration_ms": 200000,
                "artists": [{"name": "AA"}],
                "album": {"images": [{"url": "http://img/alpha.jpg"}]},
            },
        },
    )
    # Avoid network fetch
    monkeypatch.setattr(
        music, "_ensure_album_cached", lambda url, tid: "/album_art/trkA.jpg"
    )
    c = _client()
    body = c.get("/v1/state", headers=_auth()).json()
    assert body["is_playing"] is True
    assert body["track"]["id"] == "trkA"
    assert body["track"]["duration_ms"] == 200000


def test_queue_mapping_spotify(monkeypatch):
    import app.api.music as music

    monkeypatch.setattr(music, "PROVIDER_SPOTIFY", True)
    monkeypatch.setattr(
        music,
        "_provider_queue",
        lambda uid: (
            {
                "item": {
                    "id": "cur1",
                    "name": "C",
                    "artists": [{"name": "X"}],
                    "album": {"images": []},
                }
            },
            [
                {
                    "id": "n1",
                    "name": "N1",
                    "artists": [{"name": "Y"}],
                    "album": {"images": []},
                },
                {
                    "id": "n2",
                    "name": "N2",
                    "artists": [{"name": "Z"}],
                    "album": {"images": []},
                },
            ],
        ),
    )
    monkeypatch.setattr(music, "_ensure_album_cached", lambda url, tid: None)
    c = _client()
    body = c.get("/v1/queue", headers=_auth()).json()
    assert body["current"]["id"] == "cur1"
    assert len(body["up_next"]) == 2


def test_recommendations_filtering_explicit(monkeypatch):
    import app.api.music as music
    from app.models.music_state import load_state, save_state

    monkeypatch.setattr(music, "PROVIDER_SPOTIFY", True)
    # Seed last_track_id for seeds
    st = load_state("u_test")
    st.last_track_id = "seed123"
    st.vibe.explicit = False
    save_state("u_test", st)
    tracks = [
        {
            "id": "e1",
            "name": "E",
            "artists": [],
            "album": {"images": []},
            "explicit": True,
        },
        {
            "id": "c1",
            "name": "C",
            "artists": [],
            "album": {"images": []},
            "explicit": False,
        },
    ]
    monkeypatch.setattr(
        music,
        "_provider_recommendations",
        lambda uid, seed_tracks=None, vibe=None, limit=10: tracks,
    )
    c = _client()
    out = c.get("/v1/recommendations", headers=_auth()).json()
    ids = [r["id"] for r in out["recommendations"]]
    assert "c1" in ids and "e1" not in ids


def test_recommendations_limit_clamp(monkeypatch):
    import app.api.music as music

    monkeypatch.setattr(music, "PROVIDER_SPOTIFY", True)
    # Bust cache from prior tests
    st = load_state("u_test")
    st.last_recommendations = None
    st.recs_cached_at = None
    save_state("u_test", st)
    many = [
        {
            "id": f"t{i}",
            "name": "",
            "artists": [],
            "album": {"images": []},
            "explicit": False,
        }
        for i in range(25)
    ]
    monkeypatch.setattr(
        music,
        "_provider_recommendations",
        lambda uid, seed_tracks=None, vibe=None, limit=10: many,
    )
    c = _client()
    out = c.get("/v1/recommendations?limit=50", headers=_auth()).json()
    assert len(out["recommendations"]) == 10


def test_set_device_calls_transfer_when_spotify(monkeypatch):
    import app.api.music as music

    calls = {"transfer": 0}

    class _Stub(music.SpotifyClient):
        async def transfer(self, device_id: str, play: bool = True) -> bool:  # type: ignore[override]
            calls["transfer"] += 1
            return True

    monkeypatch.setattr(music, "PROVIDER_SPOTIFY", True)
    monkeypatch.setattr(music, "SpotifyClient", _Stub)
    c = _client()
    r = c.post("/v1/music/device", json={"device_id": "devX"}, headers=_auth())
    assert r.status_code == 200
    assert calls["transfer"] == 1


def test_volume_without_value_returns_400():
    c = _client()
    r = c.post("/v1/music", json={"command": "volume"}, headers=_auth())
    assert r.status_code == 400


def test_unknown_command_returns_400():
    c = _client()
    r = c.post("/v1/music", json={"command": "boost"}, headers=_auth())
    assert r.status_code == 400


def test_restore_clamps_to_quiet_cap(monkeypatch):
    import app.api.music as music
    from app.models.music_state import load_state, save_state

    monkeypatch.setattr(music, "_in_quiet_hours", lambda now=None: True)
    st = load_state("u_test")
    st.duck_from = 90
    st.vibe.energy = 0.8
    save_state("u_test", st)
    c = _client()
    c.post("/v1/music/restore", headers=_auth())
    after = c.get("/v1/state", headers=_auth()).json()["volume"]
    assert after <= 30


def test_temporary_volume_twice_restores_first(monkeypatch):
    import app.api.music as music

    monkeypatch.setattr(music, "_in_quiet_hours", lambda now=None: False)
    c = _client()
    c.post("/v1/vibe", json={"energy": 0.7}, headers=_auth())
    c.post("/v1/music", json={"command": "volume", "volume": 50}, headers=_auth())
    c.post(
        "/v1/music",
        json={"command": "volume", "volume": 10, "temporary": True},
        headers=_auth(),
    )
    c.post(
        "/v1/music",
        json={"command": "volume", "volume": 12, "temporary": True},
        headers=_auth(),
    )
    c.post("/v1/music/restore", headers=_auth())
    after = c.get("/v1/state", headers=_auth()).json()["volume"]
    assert after == 50


def test_state_radio_fields_present_when_fallback(monkeypatch):
    import app.api.music as music

    monkeypatch.setattr(music, "PROVIDER_SPOTIFY", False)
    monkeypatch.setattr(music, "MUSIC_FALLBACK_RADIO", True)
    monkeypatch.setattr(music, "RADIO_URL", "http://radio.local/stream.mp3")
    c = _client()
    body = c.get("/v1/state", headers=_auth()).json()
    assert body.get("provider") == "radio"
    assert body.get("radio_url") == "http://radio.local/stream.mp3"


def test_queue_empty_and_count_zero_when_provider_off():
    c = _client()
    body = c.get("/v1/queue", headers=_auth()).json()
    assert body["up_next"] == [] and body["skip_count"] >= 0


def test_music_ws_ping_pong():
    with _client().websocket_connect("/v1/ws/music") as ws:
        ws.send_text("ping")
        out = ws.receive_text()
        assert out == "pong"


def test_vibe_defaults_turn_up_and_uplift(monkeypatch):
    c = _client()
    c.post("/v1/vibe", json={"name": "Turn Up"}, headers=_auth())
    st = c.get("/v1/state", headers=_auth()).json()
    assert abs(st["vibe"]["energy"] - 0.9) < 1e-6
    c.post("/v1/vibe", json={"name": "Uplift Morning"}, headers=_auth())
    st2 = c.get("/v1/state", headers=_auth()).json()
    assert abs(st2["vibe"]["energy"] - 0.6) < 1e-6


def test_explicit_allowed_respects_global_disable(monkeypatch):
    import app.api.music as music

    monkeypatch.setattr(music, "EXPLICIT_DEFAULT", False)
    c = _client()
    c.post("/v1/vibe", json={"explicit": True}, headers=_auth())
    st = c.get("/v1/state", headers=_auth()).json()
    assert st["explicit_allowed"] is False


def test_state_includes_device_id_after_set():
    c = _client()
    c.post("/v1/music/device", json={"device_id": "dev-9"}, headers=_auth())
    st = c.get("/v1/state", headers=_auth()).json()
    assert st["device_id"] == "dev-9"
