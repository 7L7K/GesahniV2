# Domain: AUTH

## Current Purpose

The AUTH domain handles user authentication and authorization for the GesahniV2 application. It provides:

- **Local user authentication** via username/password with bcrypt hashing and SQLite storage
- **OAuth integration** with Google, Spotify, and Apple providers
- **JWT token management** with access and refresh token patterns
- **Session management** with opaque session IDs for security
- **Rate limiting** and throttling to prevent abuse
- **CSRF protection** for state-changing operations
- **Multi-tenant token storage** with encryption for third-party service tokens
- **Role-based access control** with scope enforcement
- **Audit logging** and monitoring of authentication events

## Entry Points (Routes, Hooks, Startup Tasks)

### HTTP API Endpoints

- **`/register`** (POST) → `app.auth.register()` - Create new local user account
- **`/login`** (POST) → `app.auth.login()` - Local username/password authentication
- **`/refresh`** (POST) → `app.api.auth.refresh()` - Refresh JWT access tokens
- **`/logout`** (POST) → `app.api.auth.logout()` - Clear authentication cookies
- **`/whoami`** (GET) → `app.api.auth.whoami_impl()` - Get current user identity
- **`/auth/finish`** (POST) → `app.api.auth.finish_clerk_login()` - Complete OAuth login flow
- **`/pats`** (GET/POST) → `app.api.auth.list_pats()` / `create_pat()` - Personal Access Token management
- **`/pats/{pat_id}`** (DELETE) → `app.api.auth.revoke_pat()` - Revoke PATs
- **`/auth/login`** (POST) → `app.api.auth.login()` - Dev login with rate limiting
- **`/auth/logout`** (POST) → `app.api.auth.logout_all()` - Logout all sessions
- **`/auth/refresh`** (POST) → `app.api.auth.refresh()` - Token refresh with CSRF protection
- **`/auth/token`** (POST) → `app.api.auth.issue_token()` - Dev token issuance

### OAuth Provider Routes

- **`/v1/google/auth/login_url`** (GET) → `app.api.google_oauth.login_url()` - Google OAuth initiation
- **`/v1/google/auth/callback`** (GET) → `app.api.google_oauth.callback()` - Google OAuth completion
- **`/v1/spotify/auth/login_url`** (GET) → `app.api.spotify_oauth.login_url()` - Spotify OAuth initiation
- **`/v1/spotify/auth/callback`** (GET) → `app.api.spotify_oauth.callback()` - Spotify OAuth completion
- **`/v1/apple/auth/login_url`** (GET) → `app.api.apple_oauth.login_url()` - Apple OAuth initiation
- **`/v1/apple/auth/callback`** (GET) → `app.api.apple_oauth.callback()` - Apple OAuth completion

### WebSocket Authentication

- **WebSocket connections** → `app.security.verify_ws()` - JWT validation for WS handshakes
- **WebSocket rate limiting** → `app.security.rate_limit_ws()` - Per-user WS rate limiting

### Startup Tasks

- **JWT secret validation** → `app.main._enforce_jwt_strength()` - Runtime JWT secret strength enforcement
- **Database schema initialization** → `app.startup.components.init_database()` - Auth table creation
- **Token store migration** → `app.auth_store_tokens.TokenDAO.ensure_schema_migrated()` - Schema updates
- **Session store initialization** → `app.session_store.get_session_store()` - Session storage setup

## Internal Dependencies

### Core Authentication Modules

- **`app.auth.py`** - Local user authentication with password hashing, rate limiting, and session management
- **`app.auth_core.py`** - JWT decoding, token extraction, and unified auth resolution
- **`app.tokens.py`** - JWT token creation facade with centralized TTL management
- **`app.auth_refresh.py`** - Refresh token rotation and replay protection
- **`app.csrf.py`** - CSRF token validation and cookie management
- **`app.cookies.py`** - Centralized cookie handling for auth tokens
- **`app.session_store.py`** - Opaque session ID mapping to JWT JTI values
- **`app.user_store.py`** - User profile and login statistics storage
- **`app.auth_store.py`** - Multi-tenant auth identities and PAT management
- **`app.auth_store_tokens.py`** - Encrypted third-party token storage and refresh
- **`app.auth_monitoring.py`** - Authentication event logging and metrics

### Security and Middleware

- **`app.security.py`** - Rate limiting, JWT validation, and scope enforcement
- **`app.middleware.stack.py`** - Authentication middleware stack setup
- **`app.middleware.rate_limit.py`** - HTTP request rate limiting
- **`app.middleware.csrf.py`** - CSRF protection middleware
- **`app.middleware.session_attach.py`** - Session context attachment

### Dependencies and Data Stores

- **`aiosqlite`** - User authentication database (`users.db`, `auth.db`)
- **`aiosqlite`** - Token storage database (`third_party_tokens.db`)
- **`passlib`** - Password hashing with bcrypt/pbkdf2 fallback
- **`jwt`** - JSON Web Token encoding/decoding
- **`cryptography`** - Token encryption for third-party credentials

## External Dependencies

### Third-Party Services

- **Google OAuth** - User authentication via Google accounts
- **Spotify OAuth** - Music service integration authentication
- **Apple OAuth** - Health and music service integration authentication
- **Redis** (optional) - Distributed rate limiting and caching

### Database Files

- **`users.db`** - Local user accounts, passwords, and profiles
- **`auth.db`** - Authentication tables (legacy compatibility)
- **`third_party_tokens.db`** - Encrypted OAuth tokens for external services
- **`sessions.db`** - Opaque session ID mappings

### Environment Variables

- **`JWT_SECRET`** - Required for JWT signing/verification
- **`JWT_ISS`** - JWT issuer claim for validation
- **`JWT_AUD`** - JWT audience claim for validation
- **`JWT_EXPIRE_MINUTES`** - Access token lifetime (default: 30)
- **`JWT_REFRESH_EXPIRE_MINUTES`** - Refresh token lifetime (default: 1440)
- **`RATE_LIMIT_PER_MIN`** - HTTP request rate limit (default: 60)
- **`RATE_LIMIT_BURST`** - Burst rate limit allowance (default: 10)
- **`CSRF_ENABLED`** - Enable CSRF protection (default: 0)
- **`REDIS_URL`** - Redis connection for distributed rate limiting

## Invariants / Assumptions

### Security Assumptions

- **JWT secrets must be ≥32 characters** in production (enforced at startup)
- **Bcrypt is preferred** for password hashing, with pbkdf2_sha256 fallback
- **Session IDs are opaque** and mapped to JWT JTI values internally
- **Access tokens are short-lived** (30 minutes default) to minimize exposure
- **Refresh tokens are long-lived** (24 hours default) for user convenience
- **Cross-site requests require intent headers** when CSRF is enabled
- **OAuth state cookies are short-lived** (5 minutes) to prevent replay attacks

### Data Integrity Assumptions

- **Database connections are async** and use WAL mode for concurrency
- **Token encryption uses envelope encryption** with configurable key versions
- **User emails are normalized** (lowercase, trimmed) for consistency
- **Unique constraints** prevent duplicate OAuth identities per provider
- **Foreign key constraints** maintain referential integrity between tables

### Performance Assumptions

- **Rate limiting is in-memory by default** with Redis fallback for scaling
- **Token refresh is atomic** using database transactions
- **Session lookups are fast** using indexed database queries
- **Audit logging is non-blocking** and doesn't impact auth performance

## Known Weirdness / Bugs

### Token Management Issues

- **Refresh token replay protection** is lenient and may allow some reuse scenarios
- **Session ID mapping** can fail silently if session store is unavailable
- **Token encryption** falls back to plaintext if crypto library is unavailable
- **OAuth callback handling** has multiple legacy paths that may conflict

### Rate Limiting Quirks

- **Rate limiting keys** can be inconsistent between HTTP and WebSocket connections
- **Burst rate limiting** uses separate buckets that may not align perfectly
- **Distributed rate limiting** degrades to in-memory if Redis is unavailable
- **Cross-test contamination** occurs when tests don't isolate rate limiting keys

### OAuth Integration Edge Cases

- **Google token refresh** may fail silently with invalid_grant errors
- **Provider issuer validation** may be inconsistent across different OAuth flows
- **Token scope merging** can lead to unexpected permission accumulation
- **Legacy OAuth callbacks** maintain compatibility but have inconsistent behavior

## Observed Behavior

### HTTP Status Codes and Responses

**Successful Authentication:**
- `200 OK` with `{"access_token": "jwt", "refresh_token": "jwt", "token_type": "bearer"}`
- Sets HttpOnly cookies: `__Host-access_token`, `__Host-refresh_token`, `__Host-__session`
- Includes user statistics in login response

**Failed Authentication:**
- `401 Unauthorized` with `{"code": "invalid_credentials", "message": "invalid credentials"}`
- `429 Too Many Requests` for rate limiting with `{"error": "rate_limited", "retry_after": seconds}`
- `400 Bad Request` for malformed requests or weak passwords

**Token Refresh:**
- `200 OK` with new tokens or empty body if rotation not needed
- `401 Unauthorized` for expired/missing refresh tokens
- `403 Forbidden` for CSRF validation failures
- `503 Service Unavailable` if session store is down

### Cookie Behavior

**Access Token Cookie:**
- Name: `__Host-access_token` (canonical) or `access_token` (legacy)
- HttpOnly: true, Secure: auto, SameSite: configured
- MaxAge: matches JWT expiration (default 30 minutes)

**Refresh Token Cookie:**
- Name: `__Host-refresh_token` (canonical) or `refresh_token` (legacy)
- HttpOnly: true, Secure: auto, SameSite: configured
- MaxAge: matches refresh token expiration (default 24 hours)

**Session Cookie:**
- Name: `__Host-__session` (canonical) or `__session` (legacy)
- HttpOnly: true, Secure: auto, SameSite: configured
- Value: opaque session ID, not JWT

### Authentication Flow Patterns

**Local Login Flow:**
1. Rate limiting check (user + IP based)
2. Exponential backoff for repeated failures
3. Password verification with timing attack protection
4. Token creation and cookie setting
5. Session ID mapping for security
6. User statistics update

**OAuth Flow:**
1. State cookie generation with CSRF protection
2. Redirect to provider with PKCE parameters
3. Callback validation with state verification
4. Token exchange and user identity creation
5. Cookie setting with session mapping
6. Redirect to application with auth completion

**Token Refresh Flow:**
1. CSRF validation for cross-site requests
2. Rate limiting check per session
3. Refresh token validation and JTI verification
4. Atomic token rotation with replay protection
5. Cookie updates with new session mapping
6. Audit logging of refresh events

## TODOs / Redesign Ideas

### Security Enhancements

- **Server-side CSRF token validation** for cross-site requests (currently TODO in code)
- **JWT key rotation** support for long-running deployments
- **Device fingerprinting** for enhanced session security
- **Multi-factor authentication** integration points
- **Password strength enforcement** standardization across providers

### Architecture Improvements

- **Unified token store** to consolidate local and OAuth token management
- **Distributed session store** to replace in-memory session mappings
- **Event-driven auth invalidation** for real-time token revocation
- **Configurable token scopes** with fine-grained permission models
- **OAuth provider abstraction** to standardize provider integrations

### Performance Optimizations

- **Token caching layer** to reduce database lookups
- **Batch token operations** for bulk refresh scenarios
- **Connection pooling** for database operations
- **Async token encryption** for high-throughput scenarios

### Monitoring and Observability

- **Token lifecycle metrics** for usage pattern analysis
- **Security event aggregation** for threat detection
- **Performance profiling** for auth operation bottlenecks
- **Distributed tracing** integration for auth flow visibility

### Developer Experience

- **Unified auth API** to simplify client integration
- **Better error messages** for common authentication failures
- **Development auth bypass** with safer defaults
- **Test utilities** for consistent auth state management
- **Documentation updates** for OAuth provider setup
