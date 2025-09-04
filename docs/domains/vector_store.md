# Domain: Vector Store

## Current Purpose

The Vector Store domain handles semantic search, embeddings generation, and vector similarity operations for the GesahniV2 application. It provides:

- **Multi-backend Vector Storage** with support for ChromaDB, Qdrant, and in-memory stores
- **Embedding Generation** using OpenAI, LLaMA, or deterministic stub backends
- **Semantic Search** with similarity scoring, filtering, and ranking
- **QA Caching** with automatic cache invalidation and TTL-based expiration
- **Memory Retrieval** for user-specific conversation history and knowledge
- **Hybrid Search** combining dense and sparse retrieval methods
- **Reranking** with local and hosted models for result quality improvement
- **Deduplication** preventing redundant vector storage and retrieval
- **Configuration Management** with unified DSN-based backend selection
- **Metrics and Observability** with detailed performance tracking

## Entry Points (Routes, Hooks, Startup Tasks)

### HTTP API Endpoints

- **`/v1/memory/ingest`** (POST) → `app.api.memory_ingest.ingest_memory()` - Ingest documents into vector store
- **`/v1/memory/search`** (GET) → `app.api.memory.search_memories()` - Search user memories
- **`/v1/rag`** (GET) → `app.api.rag.search_and_retrieve()` - RAG retrieval with vector search
- **`/v1/memories`** (GET/POST) → `app.api.memories.list_memories()` / `add_memory()` - Memory management

### Internal APIs

- **`app.memory.vector_store.add_user_memory()`** - Add text to user's memory store
- **`app.memory.vector_store.query_user_memories()`** - Semantic search user memories
- **`app.memory.vector_store.safe_query_user_memories()`** - Filtered memory queries with topic/date parsing
- **`app.memory.api.lookup_cached_answer()`** - Check semantic cache for similar questions
- **`app.memory.api.cache_answer()`** - Store Q&A pair in semantic cache

### Startup Tasks

- **Vector Store Initialization** → `app.memory.unified_store.create_vector_store()` - DSN-based backend selection
- **Embedding Backend Setup** → `app.embeddings.embed_sync()` - OpenAI/LLaMA/stub embedder initialization
- **Collection Management** → `app.memory.vector_store.qdrant._QACollection` - Qdrant collection lifecycle
- **Cache Configuration** → `app.memory.api._get_store()` - QA cache store initialization

### Background Tasks

- **Migration Jobs** → `app.jobs.migrate_chroma_to_qdrant.main()` - Data migration between backends
- **Lifecycle Management** → `app.jobs.qdrant_lifecycle.ensure_collections()` - Collection creation/maintenance
- **Cache Cleanup** → Automatic TTL-based cache expiration and cleanup

## Internal Dependencies

### Core Vector Store Modules
- **`app.memory.vector_store`** - Unified vector store interface and utilities
- **`app.memory.api`** - High-level vector store API with caching support
- **`app.memory.unified_store`** - DSN-based backend factory and configuration
- **`app.memory.chroma_store.ChromaVectorStore`** - ChromaDB implementation
- **`app.memory.vector_store.qdrant.QdrantVectorStore`** - Qdrant implementation
- **`app.memory.vector_store.dual.DualReadVectorStore`** - Dual-read fallback store

### Embedding System
- **`app.embeddings`** - Multi-backend embedding generation (OpenAI/LLaMA/stub)
- **`app.embeddings.embed_sync()`** - Synchronous embedding generation
- **`app.embeddings._embed_stub()`** - Deterministic test embeddings
- **`app.embeddings._get_llama_model()`** - LLaMA embedding model lazy loading

### Retrieval and Search
- **`app.retrieval.pipeline.run_pipeline()`** - End-to-end retrieval pipeline
- **`app.retrieval.qdrant_hybrid.dense_search()`** - Dense vector similarity search
- **`app.retrieval.qdrant_hybrid.sparse_search()`** - Sparse text-based search
- **`app.retrieval.reranker.hosted_rerank_passthrough()`** - Hosted model reranking
- **`app.retrieval.reranker.local_rerank()`** - Local model reranking

### Memory Management
- **`app.memory.memory_store.MemoryVectorStore`** - In-memory vector store for testing
- **`app.memory.memgpt`** - MemGPT integration for memory management
- **`app.adapters.memory.mem`** - Memory adapter with user isolation
- **`app.memory.memgpt.policy`** - Memory write policies and importance scoring

### Configuration and Utils
- **`app.memory.env_utils`** - Environment variable parsing and utilities
- **`app.memory.models`** - Data models for memory and vector operations
- **`app.config_runtime`** - Runtime configuration for vector store settings
- **`app.vector_store.py`** - Legacy vector store compatibility layer

## External Dependencies

### Vector Databases
- **ChromaDB** - Local vector database with embedding functions
- **Qdrant** - Distributed vector database with hybrid search
- **Chroma Cloud** - Cloud-hosted ChromaDB service

### Embedding Providers
- **OpenAI Embeddings API** - text-embedding-3-small model for production embeddings
- **LLaMA Models** - Local GGUF models via llama-cpp-python for privacy
- **Deterministic Stub** - Hash-based embeddings for testing/development

### Third-party Libraries
- **chromadb** - Python client for ChromaDB vector operations
- **qdrant-client** - Python client for Qdrant vector operations
- **llama-cpp-python** - LLaMA model inference for local embeddings
- **openai** - OpenAI API client for embeddings
- **numpy** - Vector operations and similarity calculations
- **sentence-transformers** - Alternative embedding models (optional)

### Storage Systems
- **SQLite** - Metadata storage for ChromaDB collections
- **Redis** - Optional distributed storage for Qdrant coordination
- **File System** - Local storage for ChromaDB persistence files

### Environment Configuration
- **VECTOR_DSN** - Unified DSN for vector store backend selection
- **EMBEDDING_BACKEND** - Embedding provider (openai/llama/stub)
- **CHROMA_PATH** - Local ChromaDB data directory
- **QDRANT_URL** - Qdrant server endpoint
- **SIM_THRESHOLD** - Similarity threshold for vector matching

## Invariants / Assumptions

- **DSN Configuration**: VECTOR_DSN takes precedence over legacy VECTOR_STORE env var
- **Embedding Consistency**: Same backend used for both indexing and querying vectors
- **User Isolation**: Memory queries always filtered by user_id for security
- **Similarity Threshold**: Default 0.24 similarity threshold for semantic matching
- **Cache TTL**: QA cache entries expire based on configurable TTL settings
- **Backend Fallback**: Dual-read stores attempt primary backend first, fallback to secondary
- **Collection Namespacing**: Collections prefixed with user_id for multi-tenancy
- **Vector Dimensionality**: All embeddings must have consistent dimensions per collection
- **Memory Persistence**: User memories stored with PII redaction and recovery mapping
- **Migration Safety**: Data migrations between backends preserve vector relationships

## Known Weirdness / Bugs

- **DSN Parsing Edge Cases**: Complex query parameters in VECTOR_DSN may not parse correctly
- **Embedding Backend Switching**: Switching embedding backends requires complete reindexing
- **Cache Inconsistency**: QA cache may return stale results during backend migrations
- **Memory Redaction Recovery**: PII redaction mappings may be lost during system failures
- **Dual-Read Latency**: Dual-read stores add latency even when primary backend is healthy
- **Qdrant Connection Pooling**: Connection pooling may exhaust under high concurrency
- **ChromaDB Locking**: File-based ChromaDB may have locking issues in multi-process environments
- **Similarity Score Distribution**: Similarity scores vary significantly between embedding backends
- **Memory Cleanup**: No automatic cleanup of orphaned memory entries after user deletion
- **Index Rebuild Overhead**: Full reindexing required after schema changes or corruption

## Observed Behavior

### Backend Selection Flow

**DSN Parsing:**
```python
# Parse VECTOR_DSN into backend configuration
dsn = "qdrant://host:6333?api_key=xxx&collection=kb"
config = VectorStoreConfig(dsn)
# scheme="qdrant", host="host", port=6333, params={"api_key": "xxx"}
```

**Backend Instantiation:**
```python
# Create appropriate backend based on scheme
if config.scheme == "qdrant":
    store = QdrantVectorStore(
        url=f"{config.host}:{config.port}",
        api_key=config.get_param("api_key"),
        collection=config.get_param("collection", "default")
    )
elif config.scheme == "chroma":
    store = ChromaVectorStore(path=config.path)
else:
    store = MemoryVectorStore()  # Fallback
```

### Embedding Generation Patterns

**OpenAI Backend:**
```python
# Synchronous embedding with TTL caching
response = openai_client.embeddings.create(
    input=text,
    model="text-embedding-3-small"
)
vector = response.data[0].embedding
```

**LLaMA Backend:**
```python
# Local model inference via executor
model = Llama(model_path=path, embedding=True)
vector = await asyncio.get_event_loop().run_in_executor(
    None, model.embed, text
)
```

**Stub Backend (Tests):**
```python
# Deterministic hash-based embeddings
hash_obj = hashlib.sha256(text.encode()).digest()
vector = np.frombuffer(hash_obj[:32], dtype=np.uint8).astype(np.float32).tolist()
```

### Vector Search Operations

**Semantic Search:**
```python
# Generate query embedding
query_vector = embed_sync(query_text)

# Search with similarity threshold
results = store.similarity_search(
    query_vector=query_vector,
    k=top_k,
    score_threshold=sim_threshold
)

# Filter and rank results
filtered = [r for r in results if r.score >= sim_threshold]
ranked = sorted(filtered, key=lambda x: x.score, reverse=True)
```

**Hybrid Search:**
```python
# Dense vector search
dense_results = dense_search(query_vector, k=k_dense)

# Sparse text search  
sparse_results = sparse_search(query_text, k=k_sparse)

# Combine with reciprocal rank fusion
combined = reciprocal_rank_fusion(dense_results, sparse_results)
```

### Memory Management Flow

**Memory Ingestion:**
```python
# Redact sensitive information
redacted_text, mapping = redact_pii(original_text)

# Generate embedding
vector = embed_sync(redacted_text)

# Store with metadata
memory_id = store.add(
    documents=[redacted_text],
    embeddings=[vector],
    metadatas=[{
        "user_id": user_id,
        "timestamp": time.time(),
        "redaction_map": mapping
    }],
    ids=[str(uuid.uuid4())]
)
```

**Memory Retrieval:**
```python
# Search user memories
results = query_user_memories(
    user_id=user_id,
    prompt=query,
    k=5,
    filters={"topic": "work"}  # Optional metadata filtering
)

# Apply similarity threshold
relevant = [r for r in results if similarity_score >= threshold]
```

### QA Caching Behavior

**Cache Lookup:**
```python
# Generate cache key from normalized query
cache_key = _normalized_hash(query.lower().strip())

# Check for similar cached answers
cached = lookup_cached_answer(
    normalized_query=query,
    similarity_threshold=0.8
)

if cached:
    return cached.answer  # Cache hit
```

**Cache Storage:**
```python
# Store successful Q&A pairs
cache_answer(
    question=original_query,
    answer=generated_answer,
    metadata={
        "user_id": user_id,
        "model": model_used,
        "timestamp": time.time()
    }
)
```

### Error Handling Patterns

**Backend Unavailable:**
```python
try:
    store = create_vector_store()
except Exception as e:
    if _strict_mode():
        raise  # Fatal in production
    else:
        logger.warning(f"Vector store failed, using memory: {e}")
        store = MemoryVectorStore()  # Graceful fallback
```

**Embedding Failures:**
```python
try:
    vector = embed_sync(text)
except Exception as e:
    logger.error(f"Embedding failed: {e}")
    if fallback_allowed:
        vector = _embed_stub(text)  # Deterministic fallback
    else:
        raise
```

**Search Timeouts:**
```python
try:
    results = await asyncio.wait_for(
        store.similarity_search(query, k=k),
        timeout=timeout_seconds
    )
except asyncio.TimeoutError:
    logger.warning("Vector search timeout")
    return []  # Return empty results
```

### Configuration Examples

**Local ChromaDB:**
```
VECTOR_DSN=chroma:///.chroma_data
CHROMA_EMBEDDER=length
SIM_THRESHOLD=0.6
```

**Qdrant Cloud:**
```
VECTOR_DSN=qdrant://cluster.cloud.qdrant.io:6333?api_key=xxx&collection=my_kb
EMBEDDING_BACKEND=openai
```

**Dual Read (Migration):**
```
VECTOR_DSN=dual://qdrant://host:6333?api_key=xxx&chroma_path=/data
```

### Performance Characteristics

**Latency Expectations:**
- **OpenAI Embeddings**: 200-500ms per request
- **LLaMA Embeddings**: 1000-3000ms per request (local inference)
- **Stub Embeddings**: <1ms (deterministic)
- **ChromaDB Search**: 10-50ms for small collections
- **Qdrant Search**: 5-20ms with proper indexing

**Throughput Considerations:**
- **Rate Limiting**: Respect provider API limits (OpenAI: 5000 req/min)
- **Batch Processing**: Group multiple texts for single embedding calls
- **Connection Pooling**: Reuse connections for Qdrant/ChromaDB
- **Memory Limits**: Monitor heap usage for large vector collections

### Migration and Compatibility

**ChromaDB to Qdrant:**
```python
# Export from ChromaDB
chroma_data = chroma_store.get_all()

# Transform to Qdrant format
qdrant_points = []
for item in chroma_data:
    point = PointStruct(
        id=item.id,
        vector=item.embedding,
        payload=item.metadata
    )
    qdrant_points.append(point)

# Import to Qdrant
qdrant_store.upsert(qdrant_points)
```

**Version Compatibility:**
```python
# Handle schema changes gracefully
try:
    collection = qdrant_store.get_collection(collection_name)
    if collection.config.params.vectors.size != expected_dim:
        logger.warning("Vector dimension mismatch, reindexing required")
except Exception:
    # Collection doesn't exist, create new
    qdrant_store.create_collection(...)
```

## TODOs / Redesign Ideas

### Immediate Issues
- **DSN Parameter Parsing**: Improve parsing of complex query parameters in VECTOR_DSN
- **Embedding Backend Validation**: Add runtime validation that stored vectors match current embedder
- **Cache Invalidation**: Implement proper cache invalidation during backend migrations
- **Memory Redaction Recovery**: Ensure redaction mappings are preserved during failures
- **Connection Pool Exhaustion**: Add connection pool monitoring and limits for Qdrant

### Architecture Improvements
- **Unified Search API**: Consolidate multiple search endpoints into single interface
- **Vector Schema Evolution**: Implement schema versioning for vector collections
- **Embedding Backend Switching**: Add support for incremental reindexing during backend changes
- **Memory Lifecycle Management**: Implement automatic cleanup of orphaned memories
- **Cache Warming**: Add proactive cache warming for frequently accessed queries

### Performance Optimizations
- **Batch Embedding**: Implement batch processing for multiple texts
- **Index Optimization**: Add HNSW index tuning for Qdrant collections
- **Memory Pooling**: Implement connection pooling for vector database clients
- **Caching Layers**: Add multi-level caching (memory → Redis → vector store)
- **Async Operations**: Convert synchronous vector operations to async where possible

### Reliability Enhancements
- **Health Checks**: Add vector store health monitoring and automatic failover
- **Data Validation**: Implement vector integrity checks and corruption detection
- **Backup Recovery**: Add automated backup and recovery procedures for vector data
- **Monitoring Dashboards**: Create observability dashboards for vector store performance
- **Circuit Breakers**: Implement circuit breakers for vector store backends

### Feature Enhancements
- **Hybrid Search**: Improve sparse-dense fusion algorithms and weighting
- **Reranking Models**: Expand reranking options with more local and hosted models
- **Vector Analytics**: Add analytics for vector distribution and similarity patterns
- **Multi-Modal Search**: Support for image and audio vector search
- **Federated Search**: Search across multiple vector collections simultaneously
- **Real-time Updates**: Support for real-time vector updates and streaming search
- **Query Expansion**: Implement query expansion and refinement techniques
- **Personalization**: Add user preference learning for search result ranking
- **Explainability**: Provide explanations for search result rankings and scores
