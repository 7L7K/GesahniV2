# GesahniV2 Authentication System - Complete Implementation Details

## Overview
This document contains the complete current state of the AUTH domain in GesahniV2, extracted directly from the codebase.

## Table of Contents
1. [Current Tree Structure](#current-tree-structure-auth-related-only)
2. [Database Schemas](#database-schemas-actual-not-intended)
3. [Migration Files](#migration-files)
4. [Cookie Implementation](#exact-cookie-behavior-in-code)
5. [JWT Configuration](#current-jwt-config)
6. [OAuth Implementation](#oauth-details)
7. [Rate Limiting](#rate-limit-implementation)
8. [Session Management](#session-truth)
9. [Error Codes](#error-code-catalog)
10. [Test Constraints](#test-constraints)
11. [OpenAPI Schema](#openapi--client-coupling)

---

## Current Tree Structure (Auth-Related Only)

```
app/
├── api/
│   ├── auth_password.py
│   ├── auth_router_dev.py
│   ├── auth_router_pats.py
│   ├── auth_router_refresh.py
│   ├── auth.py
│   ├── caregiver_auth.py
│   ├── google_oauth.py
│   ├── oauth_apple_stub.py
│   ├── oauth_apple.py
│   ├── oauth_google.py
│   ├── oauth_store.py
│   ├── sessions_http.py
│   ├── sessions_ws.py
│   ├── sessions.py
├── auth_core.py
├── auth_device
│   └── __init__.py
├── auth_monitoring.py
├── auth_providers.py
├── auth_refresh.py
├── auth_store_tokens.py
├── auth_store.py
├── auth.py
├── cookie_config.py
├── cookie_names.py
├── cookies.py
├── crypto_tokens.py
├── csrf.py
├── db/
│   ├── __init__.py
│   ├── migrate.py
│   └── paths.py
├── integrations/
│   ├── google/
│   │   ├── oauth.py
│   │   ├── routes.py
│   │   └── state.py
│   └── spotify/
│       └── oauth.py
├── middleware/
│   ├── cors.py
│   ├── rate_limit.py
│   └── session_attach.py
├── migrations/
│   ├── 001_create_third_party_tokens.sql
│   ├── 002_add_access_token_enc.sql
│   ├── 003_add_auth_identities.sql
├── models/
│   ├── third_party_tokens.py
│   └── user_stats.py
├── router/
│   ├── auth_api.py
├── security/
│   └── auth_contract.py
├── session_store.py
├── sessions_store.py
├── token_store.py
├── tokens.py
└── user_store.py
```

---

## Database Schemas (Actual, Not Intended)

### auth.db Schema
```sql
CREATE TABLE users (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT,
    name TEXT,
    avatar_url TEXT,
    created_at REAL NOT NULL,
    verified_at REAL,
    auth_providers TEXT
);
CREATE TABLE devices (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    device_name TEXT,
    ua_hash TEXT NOT NULL,
    ip_hash TEXT NOT NULL,
    created_at REAL NOT NULL,
    last_seen_at REAL,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    device_id TEXT NOT NULL,
    created_at REAL NOT NULL,
    last_seen_at REAL,
    revoked_at REAL,
    mfa_passed INTEGER DEFAULT 0,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY(device_id) REFERENCES devices(id) ON DELETE CASCADE
);
CREATE TABLE auth_identities (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    provider_iss TEXT,
    provider_sub TEXT,
    email_normalized TEXT,
    email_verified INTEGER DEFAULT 0,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    UNIQUE(provider, provider_iss, provider_sub),
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE TABLE pat_tokens (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    token_hash TEXT NOT NULL,
    scopes TEXT NOT NULL,
    exp_at REAL,
    created_at REAL NOT NULL,
    revoked_at REAL,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE TABLE audit_log (
    id TEXT PRIMARY KEY,
    user_id TEXT,
    session_id TEXT,
    event_type TEXT NOT NULL,
    meta TEXT,
    created_at REAL NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL,
    FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE SET NULL
);
```

### users.db Schema
```sql
CREATE TABLE users (
    user_id TEXT PRIMARY KEY,
    login_count INTEGER DEFAULT 0,
    last_login TEXT,
    request_count INTEGER DEFAULT 0,
    password_hash TEXT
);
CREATE TABLE user_stats (
    user_id TEXT PRIMARY KEY,
    login_count INTEGER DEFAULT 0,
    last_login TEXT,
    request_count INTEGER DEFAULT 0
);
CREATE TABLE auth_users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL
);
CREATE TABLE schema_migrations (
    version INTEGER PRIMARY KEY
);
CREATE TABLE device_sessions (
    sid TEXT PRIMARY KEY,
    did TEXT NOT NULL,
    user_id TEXT NOT NULL,
    device_name TEXT,
    created_at TEXT,
    last_seen TEXT,
    revoked INTEGER DEFAULT 0
);
CREATE TABLE revoked_families (
    family_id TEXT PRIMARY KEY,
    revoked_at TEXT
);
CREATE TABLE auth (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL
);
```

### third_party_tokens.db Schema
```sql
CREATE TABLE third_party_tokens (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    provider_sub TEXT,
    access_token TEXT NOT NULL,
    access_token_enc BLOB,
    refresh_token TEXT,
    refresh_token_enc BLOB,
    envelope_key_version INTEGER DEFAULT 1,
    last_refresh_at INTEGER DEFAULT 0,
    refresh_error_count INTEGER DEFAULT 0,
    scope TEXT,
    service_state TEXT,
    expires_at INTEGER NOT NULL,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    is_valid INTEGER DEFAULT 1,
    identity_id TEXT,
    provider_iss TEXT,
    scope_union_since INTEGER DEFAULT 0,
    scope_last_added_from TEXT,
    replaced_by_id TEXT
);

-- Indexes
CREATE INDEX idx_tokens_user_provider ON third_party_tokens (user_id, provider);
CREATE INDEX idx_tokens_expires_at ON third_party_tokens (expires_at);
CREATE INDEX idx_tokens_provider ON third_party_tokens (provider);
CREATE INDEX idx_tokens_valid ON third_party_tokens (is_valid);
CREATE UNIQUE INDEX idx_tokens_user_provider_iss_sub_unique ON third_party_tokens (user_id, provider, provider_iss, provider_sub) WHERE is_valid = 1;
CREATE UNIQUE INDEX ux_tokens_identity_provider_valid ON third_party_tokens (identity_id, provider) WHERE is_valid = 1;
```

### music_tokens.db Schema
```sql
CREATE TABLE music_tokens (
    user_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    access_token BLOB NOT NULL,
    refresh_token BLOB,
    scope TEXT,
    expires_at INTEGER,
    updated_at INTEGER,
    PRIMARY KEY (user_id, provider)
);
```

---

## Migration Files

### 001_create_third_party_tokens.sql
```sql
-- Migration: Create third_party_tokens table for unified token storage
CREATE TABLE IF NOT EXISTS third_party_tokens (
  id            TEXT PRIMARY KEY,
  user_id       TEXT NOT NULL,
  provider      TEXT NOT NULL,
  access_token  TEXT NOT NULL,
  refresh_token TEXT,
  scope         TEXT,
  expires_at    INTEGER NOT NULL,
  created_at    INTEGER NOT NULL,
  updated_at    INTEGER NOT NULL,
  is_valid      INTEGER DEFAULT 1
);

-- Indexes for efficient lookups
CREATE INDEX IF NOT EXISTS idx_tokens_user_provider
  ON third_party_tokens (user_id, provider);
CREATE INDEX IF NOT EXISTS idx_tokens_expires_at
  ON third_party_tokens (expires_at);
CREATE INDEX IF NOT EXISTS idx_tokens_provider
  ON third_party_tokens (provider);
CREATE INDEX IF NOT EXISTS idx_tokens_valid
  ON third_party_tokens (is_valid);

-- Ensure only one valid token per user-provider combination
CREATE UNIQUE INDEX IF NOT EXISTS idx_tokens_user_provider_unique
  ON third_party_tokens (user_id, provider)
  WHERE is_valid = 1;
```

### 002_add_access_token_enc.sql
```sql
-- Migration: Add access_token_enc column to third_party_tokens and migrate existing rows
PRAGMA foreign_keys=off;
BEGIN TRANSACTION;

ALTER TABLE third_party_tokens RENAME TO third_party_tokens_old;

CREATE TABLE third_party_tokens (
  id            TEXT PRIMARY KEY,
  user_id       TEXT NOT NULL,
  provider      TEXT NOT NULL,
  access_token  TEXT NOT NULL,
  access_token_enc BLOB,
  refresh_token TEXT,
  refresh_token_enc BLOB,
  envelope_key_version INTEGER DEFAULT 1,
  last_refresh_at INTEGER DEFAULT 0,
  refresh_error_count INTEGER DEFAULT 0,
  scope         TEXT,
  expires_at    INTEGER NOT NULL,
  created_at    INTEGER NOT NULL,
  updated_at    INTEGER NOT NULL,
  is_valid      INTEGER DEFAULT 1
);

INSERT INTO third_party_tokens (id, user_id, provider, access_token, access_token_enc, refresh_token, refresh_token_enc, envelope_key_version, last_refresh_at, refresh_error_count, scope, expires_at, created_at, updated_at, is_valid)
SELECT id, user_id, provider, access_token, NULL, refresh_token, refresh_token_enc, envelope_key_version, last_refresh_at, refresh_error_count, scope, expires_at, created_at, updated_at, is_valid
FROM third_party_tokens_old;

DROP TABLE third_party_tokens_old;

COMMIT;
PRAGMA foreign_keys=on;
```

### 003_add_auth_identities.sql
```sql
-- Migration: Add auth_identities table and link third_party_tokens -> identity_id
PRAGMA foreign_keys=off;
BEGIN TRANSACTION;

-- 1) Create canonical identities table
CREATE TABLE IF NOT EXISTS auth_identities (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  provider TEXT NOT NULL,
  provider_iss TEXT,
  provider_sub TEXT,
  email_normalized TEXT,
  email_verified INTEGER DEFAULT 0,
  created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
  updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_identity_provider ON auth_identities(provider, provider_iss, provider_sub);
CREATE INDEX IF NOT EXISTS ix_identity_email ON auth_identities(email_normalized);

-- 2) Add identity_id column to third_party_tokens (preserve user_id for compatibility/backfill)
ALTER TABLE third_party_tokens ADD COLUMN identity_id TEXT;

-- 3) Backfill: for each distinct (user_id, provider, provider_iss, provider_sub) create an identity
INSERT OR IGNORE INTO auth_identities(id, user_id, provider, provider_iss, provider_sub, email_normalized, email_verified, created_at, updated_at)
SELECT lower(hex(randomblob(16))) as id,
       user_id,
       provider,
       provider_iss,
       provider_sub,
       NULL as email_normalized,
       0 as email_verified,
       strftime('%s','now') as created_at,
       strftime('%s','now') as updated_at
FROM (
  SELECT DISTINCT user_id, provider, IFNULL(provider_iss, '') AS provider_iss, IFNULL(provider_sub, '') AS provider_sub
  FROM third_party_tokens
);

-- 4) Populate third_party_tokens.identity_id by joining on user_id+provider+provider_iss+provider_sub
UPDATE third_party_tokens
SET identity_id = (
  SELECT id FROM auth_identities ai
  WHERE ai.user_id = third_party_tokens.user_id
    AND ai.provider = third_party_tokens.provider
    AND IFNULL(ai.provider_iss,'') = IFNULL(third_party_tokens.provider_iss,'')
    AND IFNULL(ai.provider_sub,'') = IFNULL(third_party_tokens.provider_sub,'')
  LIMIT 1
)
WHERE identity_id IS NULL;

-- 5) Unique constraint for valid tokens per identity+provider
CREATE UNIQUE INDEX IF NOT EXISTS ux_tokens_identity_provider_valid ON third_party_tokens(identity_id, provider) WHERE is_valid = 1;

COMMIT;
PRAGMA foreign_keys=on;
```

---

## Exact Cookie Behavior in Code

### Cookie Helper Functions (`app/cookies.py`)

**Cookie Setting Functions:**
- `set_auth_cookies()` - Sets access_token, refresh_token, and __session cookies
- `set_oauth_state_cookies()` - Sets OAuth state cookies (g_state, g_next, g_code_verifier, g_session)
- `set_csrf_cookie()` - Sets CSRF token cookie
- `set_device_cookie()` - Sets device trust cookie
- `set_named_cookie()` - Generic cookie setter

**Cookie Reading Functions:**
- `read_access_cookie()` - Reads access token cookie (accepts GSNH_AT or access_token)
- `read_refresh_cookie()` - Reads refresh token cookie (accepts GSNH_RT or refresh_token)
- `read_session_cookie()` - Reads session cookie (accepts GSNH_SESS, __session, or session)

### Cookie Names (`app/cookie_names.py`)
```python
# Canonical names (GSNH_*)
GSNH_AT = "GSNH_AT"           # Access token
GSNH_RT = "GSNH_RT"          # Refresh token
GSNH_SESS = "GSNH_SESS"      # Session ID

# Abstract names (for test compatibility)
ACCESS_TOKEN = "access_token"
REFRESH_TOKEN = "refresh_token"
SESSION = "__session"

# Legacy names (deprecated)
ACCESS_TOKEN_LEGACY = "access_token"
REFRESH_TOKEN_LEGACY = "refresh_token"
SESSION_LEGACY = "__session"
```

### Environment Variables That Change Cookie Names/Flags
- `USE_HOST_COOKIE_PREFIX=1` - Adds `__Host-` prefix for secure, host-only cookies
- `COOKIE_SECURE=1` - Forces Secure flag (default: auto-detect)
- `COOKIE_SAMESITE=Lax|Strict|None` - Sets SameSite policy (default: Lax)
- `COOKIE_DOMAIN=domain.com` - Sets cookie domain (default: host-only)
- `COOKIE_PATH=/custom` - Sets cookie path (default: /)

### Cookie Setting Implementation
```python
# From set_auth_cookies()
# Sets both canonical GSNH_* names and legacy names for compatibility
access_header = format_cookie_header(
    key=f"{host_prefix}{GSNH_AT}",
    value=access,
    max_age=access_ttl,
    secure=cookie_config["secure"],
    samesite=cookie_config["samesite"],
    path=cookie_config["path"],
    httponly=True,
    domain=cookie_config["domain"],
)
resp.headers.append("Set-Cookie", access_header)

# Also sets abstract name for test compatibility
access_abstract_header = format_cookie_header(
    key=ACCESS_TOKEN,
    value=access,
    max_age=access_ttl,
    # ... same attributes
)
resp.headers.append("Set-Cookie", access_abstract_header)
```

---

## Current JWT Config

### Algorithm & Key Management
- **Algorithm**: HS256 (configurable via `JWT_ALGS` env var, defaults to HS256)
- **Key Source**: `JWT_SECRET` environment variable (required)
- **Key ID (kid)**: Not implemented (headers = {"kid": kid} if kid else None)
- **Validation**: Uses PyJWT library with configurable algorithms list

### JWT Configuration (`app/tokens.py`)
```python
ALGORITHM = os.getenv("JWT_ALGS", "HS256").split(",")[0].strip() or "HS256"
SECRET_KEY = os.getenv("JWT_SECRET")
JWT_ISS = os.getenv("JWT_ISS")
JWT_AUD = os.getenv("JWT_AUD")

# Token expiration times (fallback defaults)
EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "30"))
REFRESH_EXPIRE_MINUTES = int(os.getenv("JWT_REFRESH_EXPIRE_MINUTES", "1440"))
```

### Access Token Claims
```python
to_encode.update({
    "exp": expire,
    "iat": datetime.now(timezone.utc),
    "jti": uuid4().hex,  # Unique token ID
    "type": "access",
    "scopes": data.get("scopes", ["care:resident", "music:control", "chat:write"]),
})
if JWT_ISS:
    to_encode["iss"] = JWT_ISS
if JWT_AUD:
    to_encode["aud"] = JWT_AUD
```

### JWT TTLs (Code Defaults)
- **Access Token**: 30 minutes (`JWT_EXPIRE_MINUTES=30`)
- **Refresh Token**: 1440 minutes = 24 hours (`JWT_REFRESH_EXPIRE_MINUTES=1440`)

---

## OAuth Details

### OAuth Callback Routes & Code Paths

**Google OAuth:**
- **Callback Route**: `/v1/google/auth/callback`
- **Handler**: `app/integrations/google/routes.py::callback_endpoint()`
- **Code Path**:
  ```python
  # app/integrations/google/routes.py
  @router.get("/callback")
  def callback_endpoint(request: Request, code: str = None, state: str = None, error: str = None):
      # Validates state cookie, exchanges code for tokens
      # Stores tokens via TokenDAO, sets auth cookies
      # Redirects to next_url from state
  ```

**Spotify OAuth:**
- **Callback Route**: `/v1/spotify/auth/callback`
- **Handler**: `app/integrations/spotify/oauth.py` (integrated into main flow)
- **Code Path**: Similar to Google, uses unified token exchange helper

**Apple OAuth:**
- **Callback Route**: `/v1/apple/auth/callback`
- **Handler**: `app/integrations/apple/routes.py` (stub implementation)
- **Code Path**: Currently stubbed, returns placeholder response

### PKCE Implementation

**PKCE Generation** (`app/integrations/google/oauth.py`):
```python
def get_authorization_url(self, state: str, code_verifier: str | None = None) -> str:
    # Generates code_challenge from code_verifier
    import base64
    import hashlib

    if code_verifier:
        code_challenge = base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode()).digest()
        ).decode().rstrip('=')

        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": self.redirect_uri,
            "scope": self.scopes,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "access_type": "offline",
            "include_granted_scopes": "true",
            "prompt": "consent",
        }
```

**PKCE Validation** (`app/integrations/google/oauth.py`):
```python
async def exchange_code_for_tokens(self, code: str, code_verifier: str | None = None) -> dict[str, Any]:
    # Enforce PKCE presence and length
    if not code_verifier or not (43 <= len(code_verifier) <= 128):
        raise OAuthError(code=ERR_OAUTH_EXCHANGE_FAILED, http_status=400, reason="missing_or_invalid_pkce", extra=None)

    # Call unified async token exchange helper
    td = await async_token_exchange(code, code_verifier=code_verifier)
```

### State Cookie Details
- **Cookie Name**: `g_state` (Google), `oauth_state` (Apple), `spotify_state` (Spotify)
- **TTL**: 600 seconds (10 minutes)
- **Contents**: Signed JWT containing state, next_url, and session_id
- **Storage**: Server-side in Redis (if available) or in-memory
- **Validation**: Compares cookie value with OAuth state parameter

---

## Rate Limit Implementation

### Rate Limiting Key Format (`app/middleware/rate_limit.py`)
```python
def _key(client_ip: str, path: str, user_id: str | None) -> str:
    raw = f"{client_ip}|{path}|{user_id or 'anon'}"
    return hashlib.sha256(raw.encode()).hexdigest()
```

### Rate Limiting Implementation
- **Backend**: In-process bucket (falls back to Redis if `REDIS_URL` is set)
- **Key Format**: SHA256 hash of `client_ip|path|user_id`
- **Limits**: Configurable via `RATE_LIMIT_PER_MIN` (default: from settings)
- **Window**: Configurable via `WINDOW_SECONDS` (default: from settings)
- **Bypass**: Configurable scopes via `BYPASS_SCOPES`

### Redis vs In-Process
- **Redis**: Used when `REDIS_URL` is set, provides distributed rate limiting
- **In-Process**: Default fallback, single-process only
- **Adapter File**: `app/middleware/rate_limit.py` (handles both backends transparently)

---

## Session Truth

### Session ↔ JTI Mapping (`app/session_store.py`)

**Storage Schema:**
```python
# Redis key format
session_key = f"session:{session_id}"

# Stored payload
{
    "jti": jti,                    # JWT ID from access token
    "expires_at": expires_at,      # Unix timestamp
    "identity": {                  # Full identity payload
        "user_id": user_id,
        "sub": sub,
        "scopes": scopes,
        "exp": exp,
        # ... other claims
    },
    "created_at": created_at,
    "last_seen_at": last_seen_at,
    "refresh_fam_id": refresh_fam_id  # Optional
}
```

**Write Operation:**
```python
def create_session(self, jti: str, expires_at: float, *, identity: dict | None = None) -> str:
    session_id = f"sess_{int(time.time())}_{random.getrandbits(32):08x}"

    payload = {
        "jti": jti,
        "expires_at": expires_at,
        "identity": identity,
        "created_at": int(time.time()),
        "last_seen_at": int(time.time()),
    }

    # Store in Redis or memory
    if self._redis_client:
        self._redis_client.setex(session_key, ttl, json.dumps(payload))
    else:
        self._memory_store[session_id] = payload
```

**Read Operation:**
```python
def get_session(self, session_id: str) -> str | None:
    # Returns JTI if session exists and is valid
    data = self._redis_client.get(f"session:{session_id}")
    if data:
        session_data = json.loads(data)
        if session_data.get("expires_at", 0) > time.time():
            return session_data.get("jti")
    return None
```

### Device Creation/Reading

**Device Creation** (`app/auth_store.py`):
```python
async def create_device(
    *, id: str, user_id: str, device_name: str | None, ua_hash: str, ip_hash: str
) -> None:
    async with aiosqlite.connect(str(_db_path())) as db:
        await db.execute(
            "INSERT INTO devices(id,user_id,device_name,ua_hash,ip_hash,created_at,last_seen_at) VALUES (?,?,?,?,?,?,?)",
            (id, user_id, device_name, ua_hash, ip_hash, _now(), _now()),
        )
        await db.commit()
```

**Device Tracking:**
- `ua_hash`: SHA256 hash of User-Agent header
- `ip_hash`: SHA256 hash of client IP address
- `last_seen_at`: Updated on device access
- `device_name`: Optional human-readable name

---

## Error Code Catalog

### Error Constants (`app/error_codes.py`)
```python
BAD_REQUEST = "bad_request"
UNAUTHORIZED = "unauthorized"
FORBIDDEN = "forbidden"
NOT_FOUND = "not_found"
CONFLICT = "conflict"
INVALID_INPUT = "invalid_input"
QUOTA = "quota"
INTERNAL = "internal"
INVALID_STATE = "invalid_state"
ACCOUNT_MISMATCH = "account_mismatch"
NEEDS_RECONNECT = "needs_reconnect"
SCOPES_MISSING = "scopes_missing"
TOKEN_EXPIRED = "token_expired"
```

### Error Response Building (`app/security.py`)
```python
# Error responses are built using FastAPI's HTTPException
raise HTTPException(
    status_code=401,
    detail="unauthorized",
    headers={"WWW-Authenticate": "Bearer"}
)

# Or using problem+json format when ENABLE_PROBLEM_HANDLER=1
return JSONResponse(
    detail={"type": "unauthorized", "detail": "Invalid credentials"},
    status_code=401,
    headers={"Content-Type": "application/problem+json"}
)
```

---

## Test Constraints

### Legacy Cookie Name Tests
Tests extensively use legacy cookie names (`access_token`, `refresh_token`, `__session`) that must be maintained for backward compatibility:

- `tests/test_api_auth.py`: Sets `client.cookies.set("access_token", token)`
- `tests/test_token_validation.py`: Uses `access_token` and `refresh_token` cookies
- `tests/test_minimal_fastapi_app.py`: Reads `access_token` cookie

### CSRF Fixtures
- `tests/unit/test_csrf_unit.py`: Comprehensive CSRF test suite
- Uses `CSRFMiddleware` in test apps
- Tests both enabled and disabled CSRF states
- Validates token extraction and validation logic

### Auth Test Fixtures
- `tests/test_api_auth.py`: Full auth flow testing
- `tests/test_auth_hardening.py`: Security-focused tests
- `tests/test_token_system_verification.py`: Token validation tests
- `tests/test_oauth_flow.py`: OAuth integration tests

---

## OpenAPI / Client Coupling

### Auth Section from OpenAPI (`artifacts/test_baseline/openapi.json`)

**Whoami Endpoint** (`/v1/auth/whoami`):
```json
{
  "description": "CANONICAL: Public whoami endpoint - the single source of truth for user identity.\n\nReturns comprehensive authentication and session information including:\n\n- Authentication status and session readiness\n- User information (ID and email)\n- Authentication source (cookie, header, clerk, or missing)\n- API version for future compatibility\n\nResponse schema:\n{\n  \"is_authenticated\": bool,\n  \"session_ready\": bool,\n  \"user_id\": str | null,\n  \"user\": {\"id\": str | null, \"email\": str | null},\n  \"source\": \"cookie\" | \"header\" | \"clerk\" | \"missing\",\n  \"version\": 1\n}",
  "responses": {
    "200": {
      "description": "Successful Response",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/WhoamiResponse"
          }
        }
      }
    }
  }
}
```

**PAT Management** (`/v1/auth/pats`):
```json
{
  "description": "List all PATs for the authenticated user.\n\nReturns:\n    list[dict]: List of PATs with id, name, scopes, created_at, revoked_at (no tokens)",
  "responses": {
    "200": {
      "description": "Successful Response",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/PATListResponse"
          }
        }
      }
    }
  }
}
```

**CSRF Token Endpoint** (`/v1/csrf`):
```json
{
  "description": "Issuer endpoint for double-submit CSRF token.\n\nReturns JSON {\"csrf_token\": \"<token>\"} and sets a non-HttpOnly cookie\nvia the centralized cookie helper. Also stores token server-side for\nenhanced cross-site validation."
}
```

### Typed Client Coupling
The OpenAPI schema defines stable response shapes that any typed client would use:
- `WhoamiResponse` - Authentication status and user info
- `PATListResponse` - Personal access token listing
- `TokenResponse` - OAuth token exchange responses
- `ErrorResponse` - Standardized error format

These shapes must remain stable to avoid breaking existing clients. The current implementation uses FastAPI's automatic OpenAPI generation from endpoint type hints and Pydantic models.

---

## Key Implementation Notes

### Multi-Database Architecture
- **auth.db**: Main authentication database (users, sessions, devices, identities, PATs, audit)
- **users.db**: User statistics and legacy auth tables
- **third_party_tokens.db**: Encrypted OAuth tokens with migration support
- **music_tokens.db**: Music provider tokens (Spotify, etc.)

### Cookie Strategy
- **Dual naming**: Sets both canonical (GSNH_*) and legacy names for compatibility
- **Host-only**: Uses `__Host-` prefix when `USE_HOST_COOKIE_PREFIX=1`
- **Configuration-driven**: All cookie attributes controlled by centralized config
- **Graceful degradation**: Falls back to defaults when config unavailable

### OAuth Flow
- **PKCE required**: Enforces code_verifier presence and validates length
- **State protection**: Uses signed JWT state tokens with server-side storage
- **Multi-provider**: Unified token storage for Google, Spotify, Apple
- **Background refresh**: Cron-based proactive token renewal

### Security Architecture
- **Token encryption**: Fernet encryption for third-party tokens
- **Session isolation**: Opaque session IDs map to JWT identifiers
- **Device tracking**: Hashes UA and IP for security monitoring
- **Audit logging**: Comprehensive auth event tracking

### Migration Strategy
- **Incremental**: Each migration builds on previous schema
- **Backwards compatible**: Preserves data during schema changes
- **Indexed**: Proper indexes for performance
- **Transactional**: All migrations use transactions for safety

This document represents the complete current state of the GesahniV2 authentication system as of the time of extraction.
