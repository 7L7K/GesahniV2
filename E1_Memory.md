### Memory / Vector Store

- **Selection**: `VECTOR_STORE` chooses backend: `memory`, `chroma`, `qdrant`, `dual`, or `cloud`. Unknown/empty defaults to Chroma; strict mode can make init errors fatal.
- **Chroma**: Local `PersistentClient` (path from `CHROMA_PATH`) or `CloudClient` when `VECTOR_STORE=cloud`. Collections: `qa_cache` and `user_memories`. Embedder is `length` or OpenAI.
- **Qdrant**: Uses `QDRANT_URL`/`QDRANT_API_KEY`. Collections: `cache:qa` (QA cache) and per‑user `mem:user:{user_id}` (memories). Vectors use cosine; ensures HNSW and payload indexes.
- **Embeddings**: Writes embed the memory; reads embed the query. Chroma can embed via its OpenAI function or local `embed_sync`. Memory store uses local `embed_sync` for both.
- **Bootstrap/Migrations**: Chroma auto‑creates collections and can self‑heal a corrupt QA cache. Qdrant ensures collections, HNSW params, and payload indexes; uses `EMBED_DIM` for size.

### Receipts

1) Backend selection and defaults
```66:73:app/memory/api.py
* ``VECTOR_STORE`` env-var controls the preferred backend.
allowed = {"memory", "inmemory", "chroma", "cloud", "qdrant", "dual", ""}
chroma_path = os.getenv("CHROMA_PATH", ".chroma_data")
```

2) Unknown/empty kinds and explicit selections
```80:92:app/memory/api.py
if kind == "":
    is_pytest = ("PYTEST_CURRENT_TEST" in os.environ) or ("pytest" in sys.modules)
    requested_kind = "chroma" if chroma_path else ("memory" if is_pytest else "chroma")
elif kind == "_unknown_":
    logger.warning("Unknown VECTOR_STORE=%r; defaulting to ChromaVectorStore", raw_kind)
else:
    requested_kind = kind
```

3) Fallback policy and metrics
```121:127:app/memory/api.py
logger.warning("%s unavailable (%s: %s); falling back to MemoryVectorStore", backend_label, type(exc).__name__, exc)
... 
store = MemoryVectorStore()
```

4) Chroma cloud vs local
```176:183:app/memory/chroma_store.py
if use_cloud:
    from chromadb import CloudClient
    client = CloudClient(
        api_key=os.getenv("CHROMA_API_KEY", ""),
        tenant=os.getenv("CHROMA_TENANT_ID", ""),
        database=os.getenv("CHROMA_DATABASE_NAME", ""),
    )
```

5) Chroma collections: QA cache and user memories
```231:266:app/memory/chroma_store.py
base_cache = self._create_collection_safely("qa_cache")
self._cache = _ChromaCacheWrapper(base_cache)
...
self._user_memories = self._create_collection_safely("user_memories")
```

6) Chroma embedder selection
```195:205:app/memory/chroma_store.py
embed_kind = os.getenv("CHROMA_EMBEDDER", "length").strip().lower()
if embed_kind == "openai":
    self._embedder = chroma_ef.OpenAIEmbeddingFunction(...)
```

7) Memory store writes/read embeddings
```171:176:app/memory/memory_store.py
mem_id = str(uuid.uuid4())
self._user_memories.setdefault(user_id, []).append(
    (mem_id, memory, embed_sync(memory), time.time())
)
```

8) Qdrant QA cache collection name
```154:161:app/memory/vector_store/qdrant/__init__.py
self.cache_collection = os.getenv("QDRANT_QA_COLLECTION", "cache:qa")
try:
    self.client.get_collection(self.cache_collection)
except Exception:
    self.client.recreate_collection(...)
```

9) Qdrant per‑user collection naming
```208:210:app/memory/vector_store/qdrant/__init__.py
def _user_collection(self, user_id: str) -> str:
    return f"mem:user:{user_id}"
```

10) Qdrant collection bootstrap (metric, HNSW)
```169:177:app/memory/vector_store/qdrant/__init__.py
def _ensure_collection(self, name: str, dim: int) -> None:
    ...
    self.client.recreate_collection(
        collection_name=name,
        vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
        hnsw_config=HnswConfigDiff(...),
    )
```
