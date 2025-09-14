# Domain: Sessions / Identity

## Current Purpose

The Sessions/Identity domain handles user authentication, session management, and identity resolution for the GesahniV2 application. It provides:

- **Multi-source authentication** with JWT tokens, session cookies, and bearer tokens
- **Session lifecycle management** with opaque session IDs and identity-first architecture
- **Token management** with access/refresh token pairs and automatic rotation
- **User store** with SQLite-based user statistics and login tracking
- **Device tracking** with user agent and IP hashing for security monitoring
- **Personal Access Tokens (PATs)** with secure storage and revocation
- **OAuth provider integration** with Google, Spotify, and Apple
- **Role-based access control** with scope enforcement and granular permissions
- **Session store** with Redis-backed session mapping and in-memory fallback
- **Identity resolution** with unified user ID extraction from multiple sources
- **Audit logging** with comprehensive authentication event tracking

## Entry Points (Routes, Hooks, Startup Tasks)

### HTTP API Endpoints

- **`/v1/auth/finish`** (POST) → `app.router.auth_api.auth_finish_post()` - OAuth callback completion
- **`/auth/finish`** (GET) → `app.router.auth_api.auth_finish_get()` - OAuth callback redirect
- **`/v1/auth/login`** (POST) → `app.api.auth.login()` - Local authentication endpoint
- **`/v1/auth/refresh`** (POST) → `app.api.auth.refresh()` - Token refresh endpoint
- **`/v1/auth/logout`** (POST) → `app.api.auth.logout()` - Session logout endpoint
- **`/v1/auth/logout-all`** (POST) → `app.api.auth.logout_all()` - Global logout endpoint
- **`/v1/auth/token`** (POST) → `app.api.auth.issue_token()` - Development token issuance
- **`/v1/whoami`** (GET) → `app.api.auth.whoami_impl()` - User identity introspection
- **`/v1/pats`** (GET/POST) → `app.api.auth.list_pats()` / `create_pat()` - PAT management
- **`/v1/pats/{pat_id}`** (DELETE) → `app.api.auth.revoke_pat()` - PAT revocation

### Authentication Dependencies

- **`get_current_user_id()`** → `app.deps.user.get_current_user_id()` - FastAPI dependency for user resolution
- **`require_user()`** → `app.deps.user.require_user()` - FastAPI dependency enforcing authentication
- **`require_scope()`** → `app.auth_core.require_scope()` - FastAPI dependency for scope enforcement
- **`csrf_validate()`** → `app.auth_core.csrf_validate()` - CSRF token validation dependency

### Startup Tasks

- **Database initialization** → `app.auth_store.ensure_tables()` - SQLite schema creation for users/devices/sessions
- **User store setup** → `app.user_store.user_dao.ensure_schema_migrated()` - User statistics database setup
- **Session store initialization** → `app.session_store.get_session_store()` - Redis/in-memory session backend setup
- **Token store initialization** → `app.token_store._init_redis_client()` - Refresh token management setup
- **JWT configuration** → `app.auth_core.AuthConfig` - Authentication configuration loading

### WebSocket Integration

- **WebSocket authentication** → Token extraction from query parameters and cookies
- **Session validation** → WebSocket handshake session ID validation
- **Device tracking** → WebSocket connection device fingerprinting
- **Scope enforcement** → WebSocket message scope validation

## Internal Dependencies

### Core Authentication Modules
- **`app.auth_core`** - JWT decoding, token validation, and unified authentication resolution
- **`app.auth_store`** - SQLite-based user/device/session storage and management
- **`app.auth_store_tokens`** - Personal Access Token (PAT) storage and lifecycle
- **`app.session_store`** - Session ID to JTI mapping with Redis/in-memory backends
- **`app.token_store`** - Refresh token management with Redis persistence
- **`app.user_store`** - User statistics and login tracking with SQLite storage

### Token Management
- **`app.tokens`** - JWT token creation, encoding, and lifecycle management
- **`app.auth_refresh`** - Automatic token refresh and rotation logic
- **`app.cookie_names`** - Centralized cookie name definitions and configuration
- **`app.cookies`** - Cookie helper functions for secure cookie management
- **`app.cookie_config`** - Cookie security settings and SameSite configuration

### OAuth Integration
- **`app.integrations.google.oauth`** - Google OAuth flow implementation
- **`app.integrations.spotify.oauth`** - Spotify OAuth flow implementation
- **`app.integrations.apple.oauth`** - Apple OAuth flow implementation
- **`app.api.google_oauth`** - Google OAuth API endpoints and callbacks
- **`app.api.spotify_oauth`** - Spotify OAuth API endpoints and callbacks

### Dependency Injection
- **`app.deps.user`** - User resolution dependencies and authentication helpers
- **`app.deps.scopes`** - Scope enforcement and permission checking
- **`app.deps.clerk_auth`** - Legacy Clerk authentication (removed)
- **`app.security`** - Security utilities and JWT decoding helpers

### Monitoring and Telemetry
- **`app.auth_monitoring`** - Authentication event tracking and metrics
- **`app.metrics_auth`** - Prometheus authentication metrics collection
- **`app.logging_config`** - Authentication-specific logging configuration
- **`app.telemetry`** - Request tracing and observability helpers

## External Dependencies

### Storage Systems
- **SQLite** - Local user/device/session storage via `aiosqlite`
- **Redis** - Distributed session/token storage with in-memory fallback
- **File system** - SQLite database files and configuration storage

### Security Libraries
- **PyJWT** - JSON Web Token encoding/decoding and validation
- **bcrypt** - Password hashing for local authentication
- **secrets** - Cryptographically secure random token generation
- **hashlib** - Hash functions for user agent and IP anonymization

### Third-party Services
- **Google OAuth** - User authentication via Google identity services
- **Spotify OAuth** - User authentication via Spotify identity services
- **Apple OAuth** - User authentication via Apple identity services

### Environment Configuration
- **JWT_SECRET** - HMAC secret for JWT token signing/verification
- **JWT_PUBLIC_KEYS** - RSA public keys for JWT validation
- **REDIS_URL** - Redis connection string for distributed storage
- **AUTH_DB** - SQLite database path for user data storage
- **JWT_ISSUER/AUDIENCE** - JWT issuer and audience validation

## Invariants / Assumptions

- **User ID consistency**: `user_id` field is always a string, never None or empty for authenticated users
- **Session ID opacity**: `__session` cookie contains opaque IDs, never JWTs for security
- **Token precedence**: Authorization header > access_token cookie > __session cookie
- **JWT secret availability**: HS256 tokens require JWT_SECRET environment variable
- **Session store fallback**: Redis unavailability falls back to in-memory storage
- **Scope normalization**: Scopes stored as space-separated strings in JWT claims
- **Device fingerprinting**: User agents and IPs are hashed for privacy compliance
- **Token refresh timing**: Access tokens are refreshed when within 5-minute expiry window
- **Anonymous user handling**: `anon` is reserved value for unauthenticated requests
- **Cookie security**: All auth cookies use HttpOnly and Secure flags in production

## Known Weirdness / Bugs

- **Session ID confusion**: Multiple session ID formats (__session cookie vs X-Session-ID header)
- **Token source logging**: Authentication source logging happens after request processing
- **JWT leeway handling**: Different leeway values for access vs refresh tokens
- **Device tracking gaps**: WebSocket connections don't properly update device last_seen
- **OAuth callback race**: Concurrent OAuth callbacks can create duplicate sessions
- **Session store memory leaks**: In-memory session store grows indefinitely without cleanup
- **Legacy cookie names**: Some code paths still support deprecated cookie names
- **Identity backfilling**: Session identity updates can fail silently on Redis errors
- **Token refresh conflicts**: Multiple concurrent refresh requests can conflict
- **WebSocket auth bypass**: WebSocket authentication doesn't enforce all same rules as HTTP

## Observed Behavior

### Authentication Flow Priority

1. **Token Extraction** → Check Authorization header, access_token cookie, __session cookie
2. **JWT Validation** → Decode and validate token with appropriate leeway
3. **Session Resolution** → Map opaque session ID to stored identity/JWT payload
4. **Identity Construction** → Build user identity from token claims and session data
5. **Scope Enforcement** → Validate required scopes against token claims
6. **Device Tracking** → Update device last_seen and create new device records
7. **Session Touch** → Update session last_seen timestamp and extend TTL
8. **User Statistics** → Increment login count and update last_login timestamp
9. **Audit Logging** → Record authentication event with telemetry data
10. **Response Headers** → Set appropriate cookies and security headers

### Session Management States

**Session Creation:**
```python
# Opaque session ID: sess_{timestamp}_{random}
# Maps to JWT JTI in session store
# Contains identity payload with user_id, scopes, device info
```

**Session Validation:**
```python
# Check session exists and is not expired
# Validate associated JWT token is still valid
# Update last_seen timestamp on access
# Extend session TTL (bounded to 30 days)
```

**Session Revocation:**
```python
# Mark session as revoked in store
# Clean up associated refresh tokens
# Prevent future access with session ID
```

### Token Lifecycle

**Access Token:**
- Expires in 14 days (configurable via JWT_ACCESS_TTL_MINUTES)
- Contains user_id, scopes, device_id, session_id
- Refreshed automatically when within 5-minute expiry window
- Stored in httpOnly, secure cookie

**Refresh Token:**
- Expires in 90 days (configurable)
- Used to obtain new access tokens
- Stored in httpOnly, secure cookie
- Family-based revocation for security

**Personal Access Tokens:**
- Long-lived tokens for API access
- Stored as SHA256 hashes in database
- Can be revoked individually or by user
- Support scope restrictions

### Response Status Codes

- **200 OK**: Successful authentication/validation
- **201 Created**: New session/token created successfully
- **400 Bad Request**: Invalid token format, missing parameters
- **401 Unauthorized**: Invalid/expired token, missing authentication
- **403 Forbidden**: Insufficient scope, CSRF validation failure
- **404 Not Found**: Invalid session ID, non-existent user
- **409 Conflict**: Session/token already exists or conflicts
- **429 Too Many Requests**: Rate limiting triggered
- **500 Internal Server Error**: Database/Redis unavailable
- **503 Service Unavailable**: Authentication backend down

### Cookie Management

**Secure Cookies (Production):**
```
Set-Cookie: access_token=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...;
    Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=1209600
Set-Cookie: refresh_token=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...;
    Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=7776000
Set-Cookie: __session=sess_1640995200_abc123def;
    Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=2592000
```

**Development Cookies:**
```
Set-Cookie: access_token=...; Path=/; HttpOnly; SameSite=Lax; Max-Age=1209600
Set-Cookie: refresh_token=...; Path=/; HttpOnly; SameSite=Lax; Max-Age=7776000
Set-Cookie: __session=...; Path=/; HttpOnly; SameSite=Lax; Max-Age=2592000
```

## TODOs / Redesign Ideas

### Immediate Issues
- **Server-side CSRF validation**: Implement server-side CSRF token validation for cross-site requests (app/api/auth.py:2032)
- **Session store cleanup**: Implement automatic cleanup for in-memory session store to prevent memory leaks
- **WebSocket device tracking**: Ensure WebSocket connections properly update device last_seen timestamps
- **OAuth callback deduplication**: Add request deduplication for concurrent OAuth callbacks
- **Legacy cookie migration**: Complete migration away from legacy cookie names

### Architecture Improvements
- **Unified session format**: Consolidate session ID formats and eliminate confusion between __session and X-Session-ID
- **Token refresh coordination**: Implement coordination mechanism to prevent concurrent refresh conflicts
- **Identity store abstraction**: Abstract identity storage behind interface to support multiple backends
- **Device fingerprinting enhancement**: Add more comprehensive device fingerprinting for security monitoring
- **Session event streaming**: Implement real-time session event streaming for monitoring

### Security Enhancements
- **Token binding**: Implement token binding to prevent token replay attacks
- **Device authorization**: Add explicit device authorization flows for new devices
- **Session fingerprinting**: Add session fingerprinting to detect session hijacking
- **OAuth state validation**: Strengthen OAuth state parameter validation and storage
- **PAT rotation**: Implement automatic PAT rotation with configurable lifetimes

### Observability Improvements
- **Authentication metrics**: Add detailed metrics for authentication success/failure rates by provider
- **Session analytics**: Implement session lifecycle analytics and abandonment tracking
- **Token usage patterns**: Track token usage patterns for security anomaly detection
- **Device intelligence**: Build device intelligence for fraud detection and user experience
- **Audit trail correlation**: Improve correlation between authentication events and application actions

### Future Capabilities
- **Multi-factor authentication**: Add TOTP/SMS/WebAuthn support for enhanced security
- **Identity federation**: Support SAML/OIDC identity providers beyond OAuth
- **Session management UI**: Build user-facing session management interface
- **Device management**: Allow users to view and revoke access from specific devices
- **Advanced PAT features**: Add PAT usage analytics, expiration policies, and scope management
