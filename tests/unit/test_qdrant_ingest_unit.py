from __future__ import annotations

import sys
import types
from typing import Any

# Provide a minimal stub for app.adapters.metrics to avoid optional voice deps
_M = type(
    "_M",
    (),
    {
        "labels": lambda self, *a, **k: self,
        "inc": lambda self, amount=1.0: None,
        "observe": lambda self, amount=0.0: None,
    },
)
sys.modules.setdefault(
    "app.adapters.metrics",
    types.SimpleNamespace(
        TTS_REQUEST_COUNT=_M(), TTS_LATENCY_SECONDS=_M(), TTS_COST_USD=_M()
    ),
)

import pytest


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    # Default to non-stub so ingest follows the Qdrant code path; override per-test
    monkeypatch.setenv("EMBEDDING_BACKEND", "openai")
    # Ensure no real Qdrant URL/api key are used
    monkeypatch.setenv("QDRANT_URL", "http://localhost:6333")
    monkeypatch.setenv("QDRANT_API_KEY", "")
    # Avoid importing router/test global setup pulling optional voice deps
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "1")
    yield


def _stub_qdrant_bindings():
    class Distance:
        COSINE = "cosine"

    class VectorParams:
        def __init__(self, size: int, distance: str) -> None:
            self.size = size
            self.distance = distance

        def __repr__(self) -> str:  # pragma: no cover
            return f"VectorParams(size={self.size}, distance={self.distance})"

    # Placeholder types for tuple contract
    class PointStruct:  # simple placeholder signature compat
        def __init__(self, id: str, vector: list[float], payload: dict[str, Any]) -> None:
            self.id = id
            self.vector = vector
            self.payload = payload

    QdrantClient = object  # unused in our tests

    class MatchValue:
        def __init__(self, value=None):
            self.value = value

    class FieldCondition:
        def __init__(self, key=None, match=None):
            self.key = key
            self.match = match

    class Filter:
        def __init__(self, must=None):
            self.must = must or []
    return QdrantClient, Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue


def test_sanitize_collection_name(monkeypatch):
    from app.ingest import markitdown_ingest as mi

    assert mi._sanitize_collection_name("kb:test") == "kb_test"
    assert mi._sanitize_collection_name("A B/C") == "A_B_C"
    assert mi._sanitize_collection_name("ok_name-1.2") == "ok_name-1.2"


def test_ensure_collection_stub_drops_and_creates(monkeypatch):
    from app.ingest import markitdown_ingest as mi

    # Force stub behavior
    monkeypatch.setenv("EMBEDDING_BACKEND", "stub")
    monkeypatch.setattr(mi, "_lazy_qdrant", _stub_qdrant_bindings)

    calls: list[tuple[str, tuple, dict]] = []

    class Fake:
        def delete_collection(self, **kw):
            calls.append(("delete", (), kw))

        def create_collection(self, **kw):
            calls.append(("create", (), kw))

        def create_payload_index(self, **kw):
            calls.append(("index", (), kw))

    c = Fake()
    mi._ensure_collection(c, "kb:test", 8)

    # First call should be delete (best-effort), then create with size=8
    assert any(name == "create" and kw.get("collection_name") == "kb_test" and getattr(kw.get("vectors_config"), "size", None) == 8 for name, _, kw in calls)


def test_ensure_collection_non_stub_get_then_recreate(monkeypatch):
    from app.ingest import markitdown_ingest as mi

    monkeypatch.setattr(mi, "_lazy_qdrant", _stub_qdrant_bindings)

    calls: list[str] = []

    class Fake:
        def __init__(self) -> None:
            self._exists = False

        def get_collection(self, name):
            calls.append("get")
            if not self._exists:
                raise RuntimeError("nope")

        def recreate_collection(self, **kw):
            calls.append("recreate")
            self._exists = True

        def create_payload_index(self, **kw):
            calls.append("index")

    c = Fake()
    mi._ensure_collection(c, "kb:test", 16)
    assert "get" in calls and "recreate" in calls


def test_ingest_uses_detected_vector_dim_and_uuid_ids(monkeypatch):
    from app.ingest import markitdown_ingest as mi

    # Stub out qdrant bindings and embedder
    monkeypatch.setattr(mi, "_lazy_qdrant", _stub_qdrant_bindings)

    def fake_embed_many(texts):
        # Return 3 chunks, vectors of length 12
        return [[0.0] * 12 for _ in texts]

    monkeypatch.setattr(mi, "_embed_many", fake_embed_many)

    # Fake client that records upserts
    records = {}

    class Fake:
        def get_collection(self, name):
            raise RuntimeError("missing")

        def recreate_collection(self, **kw):
            records["recreated_size"] = getattr(kw.get("vectors_config"), "size", None)

        def create_payload_index(self, **kw):
            pass

        def scroll(self, **kw):
            # No dedup on first insert
            return [], None

        def upsert(self, **kw):
            records["upsert_collection"] = kw.get("collection_name")
            pts = kw.get("points") or []
            records["point_count"] = len(pts)
            # Validate id is uuid string and vector length 12
            if pts:
                records["id_is_str"] = isinstance(pts[0].id, str) if hasattr(pts[0], "id") else isinstance(pts[0]["id"], str)
                vec = pts[0].vector if hasattr(pts[0], "vector") else pts[0]["vector"]
                records["vec_len"] = len(vec)

    monkeypatch.setattr(mi, "_qdrant_client", lambda: Fake())

    res = mi.ingest_markdown_text(user_id="u1", text="# Title\n\nBody.", source="t", collection="kb:test")
    assert res["status"] == "ok"
    # Size should match detected embed length (12)
    assert records["recreated_size"] == 12
    # Sanitized name used
    assert records["upsert_collection"] == "kb_test"
    # We inserted some points with string UUID ids and correct vector length
    assert records["point_count"] >= 1
    assert records.get("id_is_str") is True
    assert records.get("vec_len") == 12


def test_dedup_skips_second_ingest(monkeypatch):
    from app.ingest import markitdown_ingest as mi

    monkeypatch.setattr(mi, "_lazy_qdrant", _stub_qdrant_bindings)

    def fake_embed_many(texts):
        return [[0.0] * 8 for _ in texts]

    monkeypatch.setattr(mi, "_embed_many", fake_embed_many)

    class Fake:
        def __init__(self) -> None:
            self._dedup = False

        def get_collection(self, name):
            raise RuntimeError("missing")

        def recreate_collection(self, **kw):
            pass

        def create_payload_index(self, **kw):
            pass

        def scroll(self, **kw):
            # Return empty on first call, then a non-empty list to signal dedup
            if not self._dedup:
                self._dedup = True
                return [], None
            # Simulate an existing point found
            return ([{"id": "x"}], None)

        def upsert(self, **kw):
            pass

    fake = Fake()
    monkeypatch.setattr(mi, "_qdrant_client", lambda: fake)

    text = "# H\n\nA"
    first = mi.ingest_markdown_text(user_id="u1", text=text, source="t", collection="kb:test")
    assert first["status"] == "ok"
    second = mi.ingest_markdown_text(user_id="u1", text=text + "\n\nAppend new line", source="t", collection="kb:test")
    assert second["status"] == "skipped"


def test_ingest_stub_backend_skips_and_returns_headings(monkeypatch):
    from app.ingest import markitdown_ingest as mi

    monkeypatch.setenv("EMBEDDING_BACKEND", "stub")

    def fake_split(text: str, max_tokens: int = 800):
        return ["# Title\nBody"], ["Title"]

    monkeypatch.setattr(mi, "_split_markdown", fake_split)

    res = mi.ingest_markdown_text(user_id="u", text="# Title\nBody", source="s", collection="c")
    assert res["status"] == "skipped"
    assert res["headings"] == ["Title"]
    assert res["chunk_count"] == 0


def test_dedup_fallback_without_filter_calls_scroll_without_filter(monkeypatch):
    from app.ingest import markitdown_ingest as mi

    # _lazy_qdrant returns classes but Filter/FieldCondition/MatchValue are None to trigger fallback path
    class QC:
        def __init__(self, url: str, api_key: str) -> None:
            self.url = url
            self.api_key = api_key

    class Distance:
        COSINE = "cosine"

    class VectorParams:
        def __init__(self, size: int, distance: str) -> None:
            self.size = size
            self.distance = distance

    class PointStruct:
        def __init__(self, id: str, vector: list[float], payload: dict[str, Any]) -> None:
            self.id = id
            self.vector = vector
            self.payload = payload

    monkeypatch.setattr(mi, "_lazy_qdrant", lambda: (QC, Distance, VectorParams, PointStruct, None, None, None))

    # Embed returns vectors of length 5
    monkeypatch.setattr(mi, "_embed_many", lambda texts: [[0.0] * 5 for _ in texts])

    called = {}

    class Fake:
        def get_collection(self, name):
            raise RuntimeError("missing")

        def recreate_collection(self, **kw):
            pass

        def create_payload_index(self, **kw):
            pass

        def scroll(self, **kw):
            # Expect no scroll_filter kw in fallback path
            called["has_filter"] = "scroll_filter" in kw
            return [], None

        def upsert(self, **kw):
            pass

    monkeypatch.setattr(mi, "_qdrant_client", lambda: Fake())
    res = mi.ingest_markdown_text(user_id="u", text="# T\n\nB", source="s", collection="kb:test")
    assert res["status"] == "ok"
    assert called.get("has_filter") is False


def test_ensure_collection_creates_payload_indexes(monkeypatch):
    from app.ingest import markitdown_ingest as mi

    monkeypatch.setattr(mi, "_lazy_qdrant", _stub_qdrant_bindings)

    fields = []

    class Fake:
        def get_collection(self, name):
            raise RuntimeError("missing")

        def recreate_collection(self, **kw):
            pass

        def create_payload_index(self, **kw):
            fields.append(kw.get("field_name"))

    c = Fake()
    mi._ensure_collection(c, "kb:test", 8)
    # Keyword indexes attempted (best-effort); 'created_at' may be keyword or float depending on backend
    for f in ("user_id", "type", "source", "created_at", "doc_hash"):
        assert f in fields


def test_split_markdown_enforces_token_budget(monkeypatch):
    # Force count_tokens to count 1 per word
    import app.token_utils as tu
    from app.ingest import markitdown_ingest as mi

    monkeypatch.setattr(tu, "count_tokens", lambda s, *_a, **_k: max(1, len(s.split())))

    text = "# H\n\n" + ("para\n\n" * 10)
    chunks, heads = mi._split_markdown(text, max_tokens=3)
    # Expect multiple chunks due to budget
    assert len(chunks) >= 3


