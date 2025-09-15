import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Test defaults
os.environ.setdefault("JWT_OPTIONAL_IN_TESTS", "1")
os.environ.setdefault("JWT_SECRET", "")
os.environ.setdefault("REQUIRE_JWT", "0")
os.environ.setdefault("VECTOR_STORE", "memory")
os.environ.setdefault("PROVIDER_SPOTIFY", "false")

from fastapi.testclient import TestClient

from app.main import app
from app.models.music_state import load_state, save_state


def _client():
    return TestClient(app)


def test_volume_cap_in_quiet_hours(monkeypatch):
    # Force quiet-hours true
    import app.api.music as music

    monkeypatch.setattr(music, "_in_quiet_hours", lambda now=None: True)
    client = _client()
    # Set high-energy vibe to increase base cap (still capped by quiet hours at 30)
    r = client.post(
        "/v1/vibe",
        json={"name": "Turn Up", "energy": 0.95, "tempo": 130, "explicit": False},
    )
    assert r.status_code == 200
    # Attempt to set volume above cap
    r = client.post("/v1/music", json={"command": "volume", "volume": 100})
    assert r.status_code == 200
    st = client.get("/v1/state").json()
    assert st["quiet_hours"] is True
    assert st["volume"] <= 30


def test_duck_and_restore(monkeypatch):
    import app.api.music as music

    monkeypatch.setattr(music, "_in_quiet_hours", lambda now=None: False)
    client = _client()
    # Ensure a vibe with a generous cap
    client.post(
        "/v1/vibe",
        json={"name": "Uplift Morning", "energy": 0.6, "tempo": 110, "explicit": False},
    )
    # Set a baseline volume
    client.post("/v1/music", json={"command": "volume", "volume": 40})
    base = client.get("/v1/state").json()["volume"]
    assert base >= 35  # sanity (cap for 0.6 energy is ~62)
    # Duck temporarily
    client.post(
        "/v1/music", json={"command": "volume", "volume": 12, "temporary": True}
    )
    ducked = client.get("/v1/state").json()["volume"]
    assert ducked == 12
    # Restore
    client.post("/v1/music/restore")
    restored = client.get("/v1/state").json()["volume"]
    assert restored == base


def test_recommendations_cache():
    client = _client()
    # Pre-seed cache with a fake recommendation
    user_id = "anon"
    st = load_state(user_id)
    st.last_recommendations = [
        {
            "id": "t1",
            "name": "Test Track",
            "artists": "Tester",
            "art_url": None,
            "explicit": False,
        }
    ]
    st.recs_cached_at = time.time()
    save_state(user_id, st)
    r = client.get("/v1/recommendations")
    assert r.status_code == 200
    data = r.json()
    assert data["recommendations"] and data["recommendations"][0]["id"] == "t1"


def test_queue_skip_count(monkeypatch):
    import app.api.music as music

    monkeypatch.setattr(music, "_in_quiet_hours", lambda now=None: False)
    client = _client()
    # Reset skip count by saving clean state
    user_id = "anon"
    st = load_state(user_id)
    st.skip_count = 0
    save_state(user_id, st)
    # Trigger next a few times
    for _ in range(3):
        client.post("/v1/music", json={"command": "next"})
    q = client.get("/v1/queue").json()
    assert q["skip_count"] >= 3


def test_device_set_and_state_reflects():
    client = _client()
    # With provider disabled, devices list is empty but device selection still persists
    r = client.post("/v1/music/device", json={"device_id": "dev-1"})
    assert r.status_code == 200
    st = client.get("/v1/state").json()
    assert st["device_id"] == "dev-1"
