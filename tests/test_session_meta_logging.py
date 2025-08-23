from __future__ import annotations

import asyncio
import json
from pathlib import Path

import app.session_store as store
from app.session_manager import save_session as _save_session
from app.session_manager import start_session as _start_session


def test_capture_save_sets_transcript_uri_when_sharing_enabled(
    monkeypatch, tmp_path: Path
):
    monkeypatch.setenv("TRANSCRIPTS_SHARE", "1")
    monkeypatch.setenv("SESSIONS_DIR", str(tmp_path))
    # Point session store to tmp path for this test
    store.SESSIONS_DIR = tmp_path
    # Create session directly via manager to avoid auth concerns
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        meta = loop.run_until_complete(_start_session())  # type: ignore
    finally:
        try:
            loop.stop()
            loop.close()
        except Exception:
            pass
    sid = meta["session_id"]
    # Save transcript
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_save_session(sid, audio=None, video=None, transcript="hello 555-222-3333", tags=None))  # type: ignore
    finally:
        try:
            loop.stop()
            loop.close()
        except Exception:
            pass
    meta_path = tmp_path / sid / "meta.json"
    data = json.loads(meta_path.read_text(encoding="utf-8"))
    assert data.get("transcript_uri")
