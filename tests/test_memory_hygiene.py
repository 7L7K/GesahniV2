import time
from app.memory.memgpt import MemGPT
from app.memory import vector_store


def test_memgpt_dedup_and_maintenance(tmp_path):
    m = MemGPT(storage_path=tmp_path / "mem.json", ttl_seconds=1)
    m.store_interaction("hello", "world", session_id="s")
    m.store_interaction("hello", "world", session_id="s")
    assert len(m._data["s"]) == 1
    m._data["s"][0]["timestamp"] = time.time() - 2
    m.nightly_maintenance()
    assert m._data["s"][0]["prompt"] == "summary"


def test_memgpt_pins_persist_and_no_dedup(tmp_path):
    m = MemGPT(storage_path=tmp_path / "mem.json", ttl_seconds=1)
    m.store_interaction("hello", "world", session_id="s", tags=["pin"])
    m.store_interaction("hello", "world", session_id="s", tags=["pin"])
    # duplicates should both be stored
    assert len(m.list_pins("s")) == 2
    # make first pin very old
    m._pin_store["s"][0]["timestamp"] = time.time() - 100
    m.nightly_maintenance()
    # pins should persist through maintenance
    assert len(m.list_pins("s")) == 2

def test_memgpt_fuzzy_filter(tmp_path):
    m = MemGPT(storage_path=tmp_path / "mem.json")
    base = "The quick brown fox jumps over the lazy dog"
    m.store_interaction("p", base, session_id="s")
    m.store_interaction("p", "The quick brown fox jumps over a lazy dog", session_id="s")
    assert len(m._data["s"]) == 1
    m.store_interaction("p", "Completely unrelated response", session_id="s")
    assert len(m._data["s"]) == 2


def record_feedback(prompt: str, feedback: str) -> None:
    """Record user feedback ('up' or 'down') for a cached answer."""
    if _cache_disabled():
        return

    result = qa_cache.query(query_texts=[prompt], n_results=1)
    ids = result.get("ids", [[]])[0]
    metas = result.get("metadatas", [[]])[0]
    if not ids or not metas:
        return

    cache_id = ids[0]
    meta = metas[0] or {}
    # Preserve all existing metadata, just update feedback
    meta["feedback"] = feedback
    _qa_cache.update(ids=[cache_id], metadatas=[meta])

    if feedback == "down":
        try:
            _qa_cache.delete(ids=[cache_id])
        except Exception:
            pass
