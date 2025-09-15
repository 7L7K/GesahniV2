import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import asyncio
import json
import os

from app.history import append_history
from app.logging_config import req_id_var
from app.telemetry import LogRecord


def test_history_appends_entry(tmp_path, monkeypatch):
    hist = tmp_path / "history.json"
    monkeypatch.setattr("app.history.HISTORY_FILE", str(hist))
    token = req_id_var.set("testid")
    rec = LogRecord(
        req_id="testid", prompt="prompt", engine_used="llama", response="resp"
    )
    asyncio.run(append_history(rec))
    req_id_var.reset(token)
    with open(hist) as f:
        data = json.load(f)
    assert data[-1]["req_id"] == "testid"
    assert data[-1]["engine_used"] == "llama"
