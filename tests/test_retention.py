import json
from datetime import datetime

import app.session_manager as sm
from app.session_store import SessionStatus
import app.session_store as store


def test_archive_old_sessions(tmp_path, monkeypatch):
    monkeypatch.setattr(sm, "SESSIONS_DIR", tmp_path)
    monkeypatch.setattr(store, "SESSIONS_DIR", tmp_path)
    old_id = "2023-01-01T00-00-00"
    old_dir = tmp_path / old_id
    old_dir.mkdir()
    meta_old = {
        "session_id": old_id,
        "created_at": "2023-01-01T00:00:00Z",
        "status": SessionStatus.DONE.value,
    }
    (old_dir / "meta.json").write_text(json.dumps(meta_old))
    (old_dir / "transcript.txt").write_text("hello", encoding="utf-8")

    recent_id = "recent"
    recent_dir = tmp_path / recent_id
    recent_dir.mkdir()
    meta_recent = {
        "session_id": recent_id,
        "created_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "status": SessionStatus.DONE.value,
    }
    (recent_dir / "meta.json").write_text(json.dumps(meta_recent))

    archived = sm.archive_old_sessions(days=90)
    assert (tmp_path / "archive" / f"{old_id}.tar.gz").exists()
    assert not (tmp_path / old_id).exists()
    assert recent_dir.exists()
    assert archived
