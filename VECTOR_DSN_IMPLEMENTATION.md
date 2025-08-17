# Unified Vector Store Implementation

## Overview

This implementation provides a unified vector store configuration system using a single `VECTOR_DSN` environment variable, replacing the scattered environment variables previously used for vector store configuration.

## Key Features

### 1. Single Configuration Knob
- **VECTOR_DSN**: One environment variable to configure all vector store backends
- **Backward Compatibility**: Legacy `VECTOR_STORE` env vars still work
- **No Silent Failures**: Small retry then loud error unless explicitly allowed

### 2. DSN Formats Supported

#### Memory Store (for tests)
```
VECTOR_DSN=memory://
```

#### Local ChromaDB
```
VECTOR_DSN=chroma:///path/to/data
```

#### Chroma Cloud
```
VECTOR_DSN=chroma+cloud://tenant.database?api_key=xxx
```

#### Qdrant HTTP
```
VECTOR_DSN=qdrant://host:port?api_key=xxx
```

#### Qdrant gRPC
```
VECTOR_DSN=qdrant+grpc://host:port?api_key=xxx
```

#### Dual Read Mode
```
VECTOR_DSN=dual://qdrant://host:port?api_key=xxx&chroma_path=/path
```

### 3. Default Configuration
- **Dev Default**: `chroma:///.chroma_data` (local ChromaDB)
- **Perf/Prod**: `qdrant://host:port` (Qdrant Docker)
- **Embeddings**: `text-embedding-3-small` (dim=1536)
- **Primary Collection**: `gesahni_qa`
- **Distance Metric**: `COSINE`

## Implementation Details

### Files Created/Modified

1. **`app/memory/unified_store.py`** (NEW)
   - `VectorStoreConfig`: DSN parser
   - `create_vector_store()`: Factory function
   - `get_vector_store_info()`: Configuration info

2. **`app/memory/api.py`** (MODIFIED)
   - Updated `_get_store()` to use unified store factory
   - Maintains backward compatibility

3. **`app/health.py`** (MODIFIED)
   - New `/v1/health/vector_store` endpoint
   - Comprehensive health check with detailed info
   - Legacy endpoints redirect to unified endpoint

4. **`tests/smoke/test_vector_store_unified.py`** (NEW)
   - Smoke tests for all backends
   - Tests memory, chroma, and qdrant without code changes
   - Tests legacy compatibility and error handling

5. **`env.example`** (MODIFIED)
   - Updated with VECTOR_DSN documentation
   - Legacy vars marked as deprecated

6. **`README.md`** (MODIFIED)
   - Added VECTOR_DSN documentation
   - Updated migration examples

## Success Criteria Met

### ✅ Flip backends by changing VECTOR_DSN only
```bash
# Development
export VECTOR_DSN=chroma:///.chroma_data

# Production
export VECTOR_DSN=qdrant://qdrant.example.com:6333?api_key=your-key

# Tests
export VECTOR_DSN=memory://
```

### ✅ Health endpoint tells you exactly what's live
```json
{
  "ok": true,
  "store_type": "ChromaVectorStore",
  "config": {
    "dsn": "chroma:///.chroma_data",
    "scheme": "chroma",
    "backend": "chroma",
    "path": ".chroma_data"
  },
  "test_passed": true,
  "test_memory_id": "uuid",
  "backend_stats": {
    "backend": "chroma",
    "path": ".chroma_data"
  },
  "embedding_model": "text-embedding-3-small",
  "embedding_dim": "1536",
  "collection": "gesahni_qa",
  "distance_metric": "COSINE"
}
```

### ✅ One smoke test passes on memory, chroma, and qdrant without code changes
All smoke tests pass:
- `test_vector_store_memory_backend`
- `test_vector_store_chroma_backend`
- `test_vector_store_qdrant_backend`
- `test_vector_store_legacy_compatibility`
- `test_vector_store_default_fallback`
- `test_vector_store_error_handling`
- `test_vector_store_strict_mode`

## Migration Guide

### From Legacy to VECTOR_DSN

#### Chroma (Local)
```bash
# Old
export VECTOR_STORE=chroma
export CHROMA_PATH=.chroma_data

# New
export VECTOR_DSN=chroma:///.chroma_data
```

#### Chroma Cloud
```bash
# Old
export VECTOR_STORE=cloud
export CHROMA_API_KEY=xxx
export CHROMA_TENANT_ID=tenant
export CHROMA_DATABASE_NAME=database

# New
export VECTOR_DSN=chroma+cloud://tenant.database?api_key=xxx
```

#### Qdrant
```bash
# Old
export VECTOR_STORE=qdrant
export QDRANT_URL=http://localhost:6333
export QDRANT_API_KEY=xxx

# New
export VECTOR_DSN=qdrant://localhost:6333?api_key=xxx
```

#### Dual Mode
```bash
# Old
export VECTOR_STORE=dual
export QDRANT_URL=http://localhost:6333
export QDRANT_API_KEY=xxx
export CHROMA_PATH=.chroma_data
export VECTOR_DUAL_WRITE_BOTH=1

# New
export VECTOR_DSN=dual://qdrant://localhost:6333?api_key=xxx&chroma_path=.chroma_data&write_both=1
```

## Error Handling

### Strict Mode
```bash
export STRICT_VECTOR_STORE=1
```
- Any vector store init error is fatal
- No silent fallbacks
- Production environments default to strict mode

### Graceful Fallback
```bash
export STRICT_VECTOR_STORE=0  # or unset
```
- Falls back to MemoryVectorStore on errors
- Logs warnings but continues operation
- Suitable for development/testing

## Testing

### Run All Vector Store Tests
```bash
python -m pytest tests/smoke/test_vector_store_unified.py -v
```

### Test Specific Backend
```bash
# Memory
export VECTOR_DSN=memory:// && python -m pytest tests/smoke/test_vector_store_unified.py::test_vector_store_memory_backend -v

# Chroma
export VECTOR_DSN=chroma:///tmp/test && python -m pytest tests/smoke/test_vector_store_unified.py::test_vector_store_chroma_backend -v

# Qdrant (requires running Qdrant)
export VECTOR_DSN=qdrant://localhost:6333 && python -m pytest tests/smoke/test_vector_store_unified.py::test_vector_store_qdrant_backend -v
```

## Benefits

1. **Simplified Configuration**: One env var instead of many
2. **Clear Documentation**: DSN format is self-documenting
3. **Better Error Messages**: Specific errors for each backend
4. **Comprehensive Health Checks**: Know exactly what's running
5. **Backward Compatibility**: Existing configs still work
6. **Future-Proof**: Easy to add new backends
7. **Consistent Interface**: Same API across all backends
