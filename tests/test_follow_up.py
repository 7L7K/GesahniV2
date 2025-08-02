import os
import importlib
import asyncio
from datetime import datetime, timedelta
from pathlib import Path


def _reload(tmp_path, monkeypatch):
    monkeypatch.setenv("FOLLOW_UPS_FILE", str(tmp_path / "follow_ups.json"))
    import app.follow_up as fu
    return importlib.reload(fu)

def test_schedule_and_persist(tmp_path, monkeypatch):
    fu = _reload(tmp_path, monkeypatch)

    calls = []

    async def fake_append(record):
        calls.append(record)

    monkeypatch.setattr(fu, "append_history", fake_append)

    run_at = datetime.utcnow() + timedelta(hours=1)
    fid = fu.schedule_follow_up("test reminder", run_at, "sess1")

    # persisted to file
    data = Path(os.environ["FOLLOW_UPS_FILE"]).read_text(encoding="utf-8")
    assert fid in data

    # list returns
    items = fu.list_follow_ups("sess1")
    assert items and items[0]["id"] == fid

    # ensure scheduler has job
    assert fu.scheduler.get_job(fid) is not None

    fu.scheduler.shutdown(wait=False)

    # reload module to simulate restart
    fu = _reload(tmp_path, monkeypatch)
    assert any(item["id"] == fid for item in fu.list_follow_ups("sess1"))
    fu.scheduler.shutdown(wait=False)


def test_cancel_follow_up(tmp_path, monkeypatch):
    fu = _reload(tmp_path, monkeypatch)

    async def fake_append(record):
        pass

    monkeypatch.setattr(fu, "append_history", fake_append)

    run_at = datetime.utcnow() + timedelta(hours=1)
    fid = fu.schedule_follow_up("test", run_at, "sess1")

    assert fu.cancel_follow_up(fid)
    assert fu.list_follow_ups("sess1") == []
    fu.scheduler.shutdown(wait=False)
