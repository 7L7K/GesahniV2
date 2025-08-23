from __future__ import annotations

import time

from app.memory.profile_store import ProfileStore


def test_upsert_semantics_newest_wins(monkeypatch):
    store = ProfileStore(ttl_seconds=60)
    uid = "u_test"
    rec1 = store.upsert(uid, "favorite_color", "green", source="utterance")
    t1 = rec1["updated_at"]
    time.sleep(0.01)
    rec2 = store.upsert(uid, "favorite_color", "blue", source="ui")
    t2 = rec2["updated_at"]
    assert t2 >= t1
    assert store.get_value(uid, "favorite_color") == "blue"


def test_get_values_and_snapshot(monkeypatch):
    store = ProfileStore(ttl_seconds=1)
    uid = "u1"
    store.upsert(uid, "preferred_name", "Alex", source="import")
    vals = store.get_values(uid)
    assert vals["preferred_name"] == "Alex"
    # single-row per key invariant: dict only contains one value
    snap = store.get_snapshot(uid)
    assert set(snap.keys()) == {"preferred_name"}
    assert isinstance(snap["preferred_name"], dict)
