# Domain: Database / Stores

## Current Purpose

The Database/Stores domain handles all data persistence, storage, and retrieval operations for the GesahniV2 application. It provides:

- **Multi-database architecture** with specialized SQLite stores for different data types (auth, tokens, users, music, sessions, care)
- **Encrypted token storage** using Fernet encryption with envelope key rotation for third-party OAuth tokens
- **Unified database initialization** with centralized schema creation and migration management
- **Redis integration** for session storage with automatic fallback to in-memory storage
- **Path resolution system** with environment-driven database location management
- **Data Access Objects (DAOs)** providing consistent interfaces for CRUD operations across all stores
- **Migration system** with concurrent schema updates and backward compatibility
- **Audit logging** and comprehensive data tracking for security and compliance
- **User statistics tracking** with login counts, request counts, and activity monitoring

## Entry Points (Routes, Hooks, Startup Tasks)

### HTTP API Endpoints
- `/me` (GET) → `app.api.me.router` - Returns authenticated user info and statistics via `user_store.get_stats()`
- `/auth/me` (GET) → `app.router.auth_api.me_endpoint()` - User profile and stats via `user_store.get_by_id()`
- `/sessions` (GET) → `app.api.sessions.router` - Session listing via `session_store` operations
- `/sessions/{id}` (GET/DELETE) → `app.api.sessions.router` - Individual session management
- `/sessions/{id}/tags` (GET/POST) → `app.api.sessions_http.router` - Session tagging via database storage

### Startup Tasks
- `app.startup.components.init_database()` - Database connectivity verification
- `app.startup.components.init_database_migrations()` - Schema migration orchestration
- `app.startup.components.init_token_store_schema()` - Background token store migration
- `app.db.__init__.init_all_tables()` - Centralized table creation across all stores

### Internal API Functions
- `app.db.migrate.ensure_all_schemas_migrated()` - Migration orchestration
- `app.db.migrate.run_all_migrations()` - Concurrent schema updates
- `app.db.paths.resolve_db_path()` - Environment-aware database path resolution

## Internal Dependencies

### Core Store Modules
- `app.auth_store` - User authentication, sessions, devices, OAuth identities, PAT tokens, audit logging
- `app.user_store` - User statistics tracking (login counts, request counts, last login)
- `app.auth_store_tokens` - Encrypted third-party OAuth tokens with automatic refresh
- `app.token_store` - Redis-backed session mapping with in-memory fallback
- `app.session_store` - Session metadata and media file management
- `app.music.token_store` - Encrypted music provider tokens (Spotify, etc.)
- `app.care_store` - Care-related data persistence
- `app.alias_store` - Command alias mappings

### Utility Modules
- `app.db.paths` - Database path resolution with environment variable support
- `app.db.migrate` - Migration orchestration and schema management
- `app.crypto_tokens` - Token encryption/decryption utilities
- `app.models.third_party_tokens` - Token data models with validation
- `app.models.user_stats` - User statistics Pydantic models

### Integration Points
- `app.memory.api` - Vector store initialization and connectivity
- `app.startup.components` - Database initialization during application startup
- `app.metrics` - Database operation metrics collection

## External Dependencies

### Database Backends
- **SQLite** (aiosqlite) - Primary storage for all domain-specific data stores
- **Redis** - Session storage and caching with automatic fallback to in-memory
- **File System** - Session media storage in `sessions/` directory

### Libraries
- `aiosqlite` - Async SQLite operations for all stores
- `cryptography.fernet` - Symmetric encryption for sensitive token data
- `redis` - Redis client for session storage
- `pydantic` - Data validation for user statistics and token models

### Environment Variables
- `AUTH_DB` - Path to authentication database (default: `auth.db`)
- `USER_DB` - Path to user statistics database (default: `users.db`)
- `THIRD_PARTY_TOKENS_DB` - Path to OAuth tokens database (default: `third_party_tokens.db`)
- `MUSIC_TOKEN_DB` - Path to music provider tokens database (default: `music_tokens.db`)
- `REDIS_URL` - Redis connection string (default: `redis://localhost:6379/0`)
- `MUSIC_MASTER_KEY` - Encryption key for music tokens
- `SESSIONS_DIR` - Base directory for session media (default: `sessions/`)
- `GESAHNI_TEST_DB_DIR` - Test database directory override

## Invariants / Assumptions

### Schema Consistency
- All SQLite databases use Write-Ahead Logging (WAL) mode with busy timeout of 2500ms
- Foreign key constraints are enabled with deferred checking during transactions
- Unique constraints prevent duplicate OAuth identities per provider
- Primary keys are UUID strings for global uniqueness
- Timestamps are stored as Unix epoch seconds (integers)

### Encryption Requirements
- Third-party tokens require encryption keys for production use
- Fernet encryption uses URL-safe base64-encoded keys
- Access tokens are encrypted separately from refresh tokens
- Envelope key versioning supports future key rotation

### Path Resolution Logic
- Database paths are resolved lazily and cached per environment variable
- Test databases use temporary directories with deterministic naming
- Parent directories are created automatically with error tolerance
- Relative paths are resolved to absolute paths for consistency

### Connection Management
- SQLite connections use aiosqlite for async operations
- Redis connections fall back gracefully to in-memory storage
- Database locks are acquired with asyncio.Lock() for thread safety
- Connection pooling is implicit through aiosqlite's connection management

## Known Weirdness / Bugs

### Migration Challenges
- Schema migrations run concurrently but may conflict on shared resources
- ALTER TABLE operations in SQLite are limited and may fail on complex schemas
- Migration failures during startup can prevent application boot
- Backfill operations for missing columns may not handle all edge cases

### Encryption Edge Cases
- Token decryption failures return None without detailed error logging
- Invalid Fernet keys cause silent failures in token retrieval
- Encrypted tokens cannot be queried or searched in the database
- Key rotation is not implemented (envelope_key_version is always 1)

### Session Management Issues
- Session store falls back to in-memory without Redis availability notice
- Expired entries in local storage may accumulate without cleanup
- Session ID generation uses timestamp + random but lacks collision detection
- Device tracking relies on user agent hashing which may have collisions

### Path Resolution Problems
- Database path resolution fails silently on permission errors
- Test database cleanup is not guaranteed if tests crash
- Environment variable precedence may confuse development setups
- Path caching prevents dynamic reconfiguration during runtime

## Observed Behavior

### Database Operations
- All stores return `None` or empty dicts when records don't exist
- Update operations use `INSERT OR REPLACE` for upsert semantics
- Foreign key cascades delete related records automatically
- Transaction failures rollback all changes atomically

### Status Codes and Responses
- `200 OK` - Successful CRUD operations return data structures
- `404 Not Found` - Missing records return None/null values
- `500 Internal Server Error` - Database connection failures or constraint violations
- Migration failures during startup raise `MigrationError`

### Data Flow Patterns
- User authentication creates/updates records in auth_store with cascading effects
- OAuth token refresh updates timestamps and error counters in auth_store_tokens
- Session creation generates opaque IDs mapped to JWT identifiers
- User statistics are incremented atomically with request processing

### Error Handling
- SQLite operational errors are logged but may not surface to API consumers
- Redis connection failures trigger automatic fallback to in-memory storage
- Encryption failures return None values without user-visible errors
- Migration errors during startup can halt application initialization

## TODOs / Redesign Ideas

### Schema Evolution
- Implement proper migration versioning with rollback capabilities
- Add database health checks and connection pool monitoring
- Support for database schema validation and integrity checks
- Consider moving from multiple SQLite files to a single database with schemas

### Security Enhancements
- Implement envelope key rotation for encrypted tokens
- Add database-level encryption for sensitive user data
- Implement token expiration cleanup jobs
- Add audit logging for all database operations

### Performance Optimizations
- Add database connection pooling for high-throughput scenarios
- Implement database query caching with invalidation strategies
- Add database indexes for common query patterns
- Consider database sharding for user data at scale

### Monitoring and Observability
- Add database performance metrics and slow query logging
- Implement database backup and recovery procedures
- Add database health endpoints for monitoring systems
- Implement database size and growth tracking

### Code Quality
- Standardize error handling across all store implementations
- Add comprehensive database operation tests
- Implement database transaction boundaries more consistently
- Add type hints and validation for all database operations
