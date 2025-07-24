import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import types
from app import capture


def test_capture_runs_arecord(monkeypatch):
    called = {}

    def fake_run(cmd, check):
        called["cmd"] = cmd
        called["check"] = check

    monkeypatch.setattr(capture, "subprocess", types.SimpleNamespace(run=fake_run))
    capture.capture_audio("out.wav", duration=2)
    assert called["cmd"][0] == "arecord"
    assert "out.wav" in called["cmd"]
