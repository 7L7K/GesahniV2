import os
from app import tasks

def test_enqueue_fallback(monkeypatch):
    called = []

    def raise_err():
        raise RuntimeError("no redis")

    monkeypatch.setattr(tasks, "_get_queue", raise_err)
    monkeypatch.setattr(tasks, "transcribe_task", lambda sid: called.append(("t", sid)))
    tasks.enqueue_transcription("abc")
    assert called == [("t", "abc")]

    called.clear()
    monkeypatch.setattr(tasks, "tag_task", lambda sid: called.append(("g", sid)))
    tasks.enqueue_tag_extraction("xyz")
    assert called == [("g", "xyz")]
