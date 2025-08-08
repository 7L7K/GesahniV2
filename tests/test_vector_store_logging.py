import logging
import os
import pytest

from app.memory.memory_store import MemoryVectorStore
from app.memory.chroma_store import ChromaVectorStore


def test_memory_store_logs(caplog):
    store = MemoryVectorStore()
    store.add_user_memory("u", "hello")
    with caplog.at_level(logging.INFO, logger="app.memory.memory_store"):
        res = store.query_user_memories("u", "hello", k=1)
    assert res == ["hello"]
    messages = [r.message for r in caplog.records]
    assert any("start user_id=u" in m for m in messages)
    assert any("end user_id=u" in m and "returned=1" in m for m in messages)


def test_chroma_store_logs(caplog, tmp_path):
    pytest.importorskip("chromadb")
    os.environ["CHROMA_PATH"] = str(tmp_path)
    store = ChromaVectorStore()
    store.add_user_memory("u", "hello")
    with caplog.at_level(logging.INFO, logger="app.memory.chroma_store"):
        res = store.query_user_memories("u", "hello", k=1)
    assert res == ["hello"]
    messages = [r.message for r in caplog.records]
    assert any("start user_id=u" in m for m in messages)
    assert any("end user_id=u" in m and "returned=1" in m for m in messages)
