import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

os.environ.setdefault("JWT_OPTIONAL_IN_TESTS", "1")
os.environ.setdefault("JWT_SECRET", "")
os.environ.setdefault("REQUIRE_JWT", "0")
os.environ.setdefault("VECTOR_STORE", "memory")
os.environ.setdefault("PROVIDER_SPOTIFY", "false")

from fastapi.testclient import TestClient

from app.main import app
from app.models.music_state import MusicState, load_state, save_state


def _client():
    return TestClient(app)


def _reset_state():
    st = MusicState.default()
    save_state("anon", st)


def test_provider_none_when_both_off(monkeypatch):
    import app.api.music as music

    _reset_state()
    monkeypatch.setattr(music, "PROVIDER_SPOTIFY", False)
    monkeypatch.setattr(music, "MUSIC_FALLBACK_RADIO", False)
    c = _client()
    resp = c.get("/v1/state")
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("provider") is None


def test_provider_radio_when_fallback_on(monkeypatch):
    import app.api.music as music

    _reset_state()
    monkeypatch.setattr(music, "PROVIDER_SPOTIFY", False)
    monkeypatch.setattr(music, "MUSIC_FALLBACK_RADIO", True)
    c = _client()
    body = c.get("/v1/state").json()
    assert body.get("provider") == "radio"


def test_radio_play_pause_toggle(monkeypatch):
    import app.api.music as music

    _reset_state()
    monkeypatch.setattr(music, "PROVIDER_SPOTIFY", False)
    monkeypatch.setattr(music, "MUSIC_FALLBACK_RADIO", True)
    c = _client()
    c.post("/v1/music", json={"command": "play"})
    assert c.get("/v1/state").json()["is_playing"] is True
    c.post("/v1/music", json={"command": "pause"})
    assert c.get("/v1/state").json()["is_playing"] is False


def test_vibe_name_defaults_calm_night():
    _reset_state()
    c = _client()
    c.post("/v1/vibe", json={"name": "Calm Night"})
    st = c.get("/v1/state").json()
    assert abs(st["vibe"]["energy"] - 0.25) < 1e-6


def test_vibe_name_defaults_turn_up():
    _reset_state()
    c = _client()
    c.post("/v1/vibe", json={"name": "Turn Up"})
    st = c.get("/v1/state").json()
    assert abs(st["vibe"]["energy"] - 0.9) < 1e-6


def test_partial_vibe_merge_energy_only():
    _reset_state()
    c = _client()
    before = c.get("/v1/state").json()["vibe"]["name"]
    c.post("/v1/vibe", json={"energy": 0.7})
    st = c.get("/v1/state").json()
    assert st["vibe"]["name"] == before
    assert abs(st["vibe"]["energy"] - 0.7) < 1e-6


def test_explicit_allowed_true_when_vibe_explicit_true():
    _reset_state()
    c = _client()
    c.post("/v1/vibe", json={"explicit": True})
    st = c.get("/v1/state").json()
    assert st["explicit_allowed"] is True


def test_explicit_allowed_false_when_vibe_explicit_false():
    _reset_state()
    c = _client()
    c.post("/v1/vibe", json={"explicit": False})
    st = c.get("/v1/state").json()
    assert st["explicit_allowed"] is False


def test_vibe_change_caps_volume_downward(monkeypatch):
    import app.api.music as music

    _reset_state()
    monkeypatch.setattr(music, "_in_quiet_hours", lambda now=None: False)
    c = _client()
    # Start with high cap vibe and set volume high
    c.post("/v1/vibe", json={"energy": 0.95})
    c.post("/v1/music", json={"command": "volume", "volume": 85})
    # Reduce vibe to low energy which lowers cap and should clamp volume
    c.post("/v1/vibe", json={"energy": 0.2})
    st = c.get("/v1/state").json()
    assert st["volume"] <= 40


def test_restore_noop_when_no_duck():
    _reset_state()
    c = _client()
    before = c.get("/v1/state").json()["volume"]
    c.post("/v1/music/restore")
    after = c.get("/v1/state").json()["volume"]
    assert before == after


def test_album_art_cached_path_returned_when_file_exists(tmp_path, monkeypatch):
    import app.api.music as music

    _reset_state()
    # Point album dir to temp
    monkeypatch.setattr(music, "ALBUM_DIR", tmp_path)
    track_id = "trk1"
    dest = tmp_path / f"{track_id}.jpg"
    dest.write_bytes(b"jpgdata")
    # Should return the public path without network
    # Use asyncio.run for event loop safety under pytest
    out = __import__("asyncio").run(music._ensure_album_cached("http://x/y.jpg", track_id))
    assert out == f"/album_art/{track_id}.jpg"


def test_in_quiet_hours_across_midnight_true():
    from app.api.music import _in_quiet_hours

    # Defaults: 22:00 - 07:00; 23:00 should be inside
    assert _in_quiet_hours(datetime(2025, 1, 1, 23, 0)) is True


def test_in_quiet_hours_outside_daytime():
    from app.api.music import _in_quiet_hours

    assert _in_quiet_hours(datetime(2025, 1, 1, 9, 0)) is False


def test_queue_skip_count_persistence():
    _reset_state()
    c = _client()
    for _ in range(2):
        c.post("/v1/music", json={"command": "next"})
    q1 = c.get("/v1/queue").json()["skip_count"]
    q2 = c.get("/v1/queue").json()["skip_count"]
    assert q2 >= q1


def test_devices_empty_when_provider_off():
    _reset_state()
    c = _client()
    devs = c.get("/v1/music/devices").json()
    assert devs["devices"] == []


def test_set_device_overwrites_previous():
    _reset_state()
    c = _client()
    c.post("/v1/music/device", json={"device_id": "dev-1"})
    c.post("/v1/music/device", json={"device_id": "dev-2"})
    st = c.get("/v1/state").json()
    assert st["device_id"] == "dev-2"


