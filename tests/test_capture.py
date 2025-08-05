import os, sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import asyncio
import numpy as np
from pathlib import Path


def test_record_creates_file(tmp_path, monkeypatch):
    from app import capture

    class DummySD:
        @staticmethod
        def rec(frames, samplerate, channels, dtype="float32"):
            return np.zeros((frames, channels), dtype=dtype)

        @staticmethod
        def wait():
            pass

    def fake_write(fname, rate, data):
        Path(fname).write_bytes(b"data")

    monkeypatch.setattr(capture, "sd", DummySD)
    monkeypatch.setattr(capture.wavfile, "write", fake_write)

    out = tmp_path / "test.wav"
    asyncio.run(capture.record(0.01, str(out)))
    assert out.exists()
