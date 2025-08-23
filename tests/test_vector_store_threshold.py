
import sys

import pytest

print("DEBUG sys.path[0]:", sys.path[0])
from app.memory.chroma_store import ChromaVectorStore


@pytest.fixture
def store():
    s = ChromaVectorStore()
    yield s
    s.close()


def test_cache_miss_high_threshold(monkeypatch, store):
    monkeypatch.setenv("SIM_THRESHOLD", "0.95")
    store.cache_answer("1", "hello", "world")
    # Distance between "hello" and "helloo" is 1.0 -> cutoff 0.05 -> miss
    assert store.lookup_cached_answer("helloo") is None


def test_cache_hit_low_threshold(monkeypatch, store):
    monkeypatch.setenv("SIM_THRESHOLD", "0.0")
    store.cache_answer("1", "hello", "world")
    # Cutoff 1.0 -> distance 1.0 still considered a hit
    assert store.lookup_cached_answer("helloo") == "world"


def test_threshold_out_of_range(monkeypatch, caplog):
    monkeypatch.setenv("SIM_THRESHOLD", "5")
    with caplog.at_level("WARNING"):
        store = ChromaVectorStore()
    # Out-of-range values are clamped to 1.0
    assert store._dist_cutoff == 0.0
    assert "SIM_THRESHOLD" in caplog.text
