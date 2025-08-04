from app import tasks


def test_enqueue_fallback(monkeypatch):
    called = []

    def raise_err():
        raise RuntimeError("no redis")

    monkeypatch.setattr(tasks, "_get_queue", raise_err)
    monkeypatch.setattr(tasks, "_load_meta", lambda sid: {"user_id": "m"})
    monkeypatch.setattr(
        tasks, "transcribe_task", lambda sid, uid: called.append(("t", sid, uid))
    )
    tasks.enqueue_transcription("abc", "u")
    assert called == [("t", "abc", "u")]

    called.clear()
    tasks.enqueue_transcription("def")
    assert called == [("t", "def", "m")]

    called.clear()
    monkeypatch.setattr(tasks, "tag_task", lambda sid: called.append(("g", sid)))
    tasks.enqueue_tag_extraction("xyz")
    assert called == [("g", "xyz")]
