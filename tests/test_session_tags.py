import os, sys, json, asyncio
from pathlib import Path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import pytest

def test_save_session_tags(monkeypatch, tmp_path):
    import app.session_manager as sm
    import app.session_store as store

    monkeypatch.setattr(sm, "SESSIONS_DIR", tmp_path)
    monkeypatch.setattr(store, "SESSIONS_DIR", tmp_path)

    async def noop(*args, **kwargs):
        return None

    monkeypatch.setattr(sm, "append_history", noop)

    meta = store.create_session()
    session_id = meta["session_id"]

    asyncio.run(sm.save_session(session_id, transcript="hi", tags=["a", "b"]))

    meta_after = store.load_meta(session_id)
    assert meta_after.get("tags") == ["a", "b"]

    tag_file = tmp_path / session_id / "tags.json"
    assert json.loads(tag_file.read_text()) == ["a", "b"]
