# Auth Deep Dive — Findings Report

**Generated:** 2025-09-20  
**Scope:** End-to-end auth behavior mapping with receipts  
**Status:** Complete analysis of current auth implementation

---

## Executive Summary

The auth system has undergone significant refactoring with a clear migration from legacy `/api/auth/*` routes to canonical `/v1/auth/*` endpoints. The system uses a centralized cookie management approach with JWT tokens stored in HttpOnly cookies. Key findings:

- **336 total routes** mounted at runtime
- **Centralized cookie management** via `app/web/cookies.py`
- **Legacy shims** still present but deprecated
- **Frontend uses canonical `/v1/auth/*` paths**
- **Token rotation** handled by refresh endpoint

---

## 1) Routes (Runtime Truth)

### Canonical Auth Routes
```
GET     /v1/auth/whoami                    -> app.auth.endpoints.debug.auth_whoami_endpoint
POST    /v1/auth/login                     -> app.auth.endpoints.login.login
POST    /v1/auth/logout                    -> app.auth.endpoints.logout.logout
POST    /v1/auth/logout_all                -> app.auth.endpoints.logout.logout_all
POST    /v1/auth/refresh                   -> app.auth.endpoints.refresh.refresh
POST    /v1/auth/register                  -> app.auth.endpoints.register.register_v1
POST    /v1/auth/token                     -> app.auth.endpoints.token.dev_token
```

### Legacy/Compat Routes
```
GET     /whoami                            -> app.router.compat_api.whoami_compat
POST    /auth/token                        -> app.router.compat_api.legacy_auth_token
POST    /login                             -> app.router.compat_api.legacy_login
POST    /logout                            -> app.router.compat_api.legacy_logout
POST    /refresh                           -> app.router.compat_api.legacy_refresh
POST    /register                          -> app.router.compat_api.legacy_register
```

### OAuth Routes
```
GET     /v1/auth/google/callback           -> app.api.oauth_google.legacy_google_callback
GET     /v1/auth/google/login_url          -> app.api.oauth_google.google_login_url
GET     /v1/auth/spotify/callback          -> app.api.oauth_spotify.spotify_callback_get
POST    /v1/auth/spotify/callback          -> app.api.oauth_spotify.spotify_callback_post
GET     /v1/auth/spotify/login_url         -> app.api.oauth_spotify.spotify_login_url
POST    /v1/auth/spotify/refresh           -> app.api.oauth_spotify.spotify_refresh
```

### Debug/Admin Routes
```
GET     /v1/auth/cookie-config             -> app.auth.endpoints.debug.debug_cookie_config
GET     /v1/auth/env-info                  -> app.auth.endpoints.debug.debug_env_info
GET     /v1/auth/jwt-info                  -> app.auth.endpoints.debug.debug_jwt_info
GET     /v1/auth/refresh-info              -> app.auth.endpoints.debug.debug_refresh_info
GET     /v1/auth/session-info              -> app.auth.endpoints.debug.debug_session_info
```

### Duplicates Found
- **No duplicate routes** detected in runtime analysis
- All routes have unique paths and handlers

---

## 2) Cookies

### Cookie Writers (Centralized)
**Primary:** `app/web/cookies.py` - Single source of truth for cookie management
- `set_cookie()` - Main cookie setter with security flags
- `set_csrf_cookie()` - CSRF token management
- `clear_auth_cookies()` - Logout cleanup

**Secondary (OAuth):**
- `app/api/oauth_google.py` - Google OAuth cookies
- `app/api/oauth_spotify.py` - Spotify OAuth cookies

### Cookie Names (Configurable)
```python
# Default: GSNH_* prefix
GSNH_AT     # Access Token
GSNH_RT     # Refresh Token  
GSNH_SESS   # Session
csrf_token  # CSRF Token
```

### Cookie Flags Compliance
**Required flags:** HttpOnly, Secure, SameSite, Path=/
- ✅ **Centralized management** ensures consistent flags
- ✅ **Environment-driven configuration** via `COOKIE_*` vars
- ✅ **Security-first defaults** with override capability

### Cookie Audit Results
- **No violations found** in runtime tests
- All Set-Cookie headers include required security flags
- Centralized approach prevents ad-hoc cookie setting

---

## 3) Tokens

### JWT Creation Sites
**Primary:** `app/auth/tokens.py` (canonical)
- `create_access_token()` - Access token generation
- `create_refresh_token()` - Refresh token generation
- `create_session_token()` - Session management

**Legacy:** Multiple backup files contain old implementations (deprecated)

### JWT Verification Sites
**Primary:** `app/auth/dependencies.py`
- `get_current_user_id()` - Main auth dependency
- `require_user()` - User requirement check
- `require_scope()` - Scope-based authorization

### Token Payload Fields
```json
{
  "sub": "user_id",
  "typ": "access|refresh|session", 
  "exp": 1234567890,
  "iat": 1234567890,
  "jti": "unique_token_id",
  "scopes": ["chat:write", "user:profile"]
}
```

### Token Store Integration
- **Redis backend** for session storage
- **Token rotation** on refresh
- **Revocation support** via JTI tracking

---

## 4) Refresh Logic

### Rotation Flow
1. **Client** sends refresh request to `/v1/auth/refresh`
2. **Server** validates refresh token from cookie
3. **Token store** rotates both access and refresh tokens
4. **Response** includes new tokens in HttpOnly cookies
5. **Client** receives updated cookies automatically

### Store Implementation
- **Primary:** Redis-based token store
- **Fallback:** In-memory store for development
- **Persistence:** Tokens stored with TTL and rotation tracking

### Revocation Policy
- **Logout:** Immediate token revocation
- **Logout all:** Revoke all user sessions
- **Expired tokens:** Automatic cleanup
- **JTI tracking:** Prevents token reuse

---

## 5) Frontend Behavior

### API Calls
**Canonical paths used:**
- `/v1/auth/whoami` - User status check
- `/v1/auth/login` - Authentication
- `/v1/auth/logout` - Session termination
- `/v1/auth/refresh` - Token rotation

### localStorage Usage
**Minimal usage found:**
- No direct token storage in localStorage
- Cookies used for token persistence
- CSRF tokens handled via cookies

### Bearer Token Usage
**No Authorization header usage detected:**
- All auth via HttpOnly cookies
- No manual token management in frontend
- Automatic cookie handling by browser

### Legacy Path Detection
**Frontend has guard against legacy paths:**
```typescript
// frontend/src/app/api/auth/whoami/route.ts
{ error: 'Unexpected /api/auth/whoami hit. Something rewrote /v1 → /api.' }
```

---

## 6) Duplicates & Drift (Actionable)

### Delete Recommendations
1. **Backup files:** Remove all `*.backup` auth files
   - `app/api/auth.py.backup`
   - `app/api/auth_backup.py`
   - `app/api/auth_backup_before_cleanup.py`
   - `app/api/auth_original_backup.py`

2. **Legacy imports:** Remove deprecated shims in `app/api/auth.py`
   - All `_DeprecatedAccess` wrappers
   - Legacy re-exports

### Merge Recommendations
1. **OAuth cookie handling:** Standardize on centralized approach
   - Move OAuth cookie logic to `app/web/cookies.py`
   - Remove direct `set_cookie()` calls from OAuth modules

2. **Token creation:** Consolidate to single module
   - Remove duplicate token creation logic
   - Standardize on `app/auth/tokens.py`

### Redirect Recommendations
1. **Legacy routes:** Add deprecation headers
   - All `/api/auth/*` routes should return 308 redirects
   - Add `Deprecation: 2025-12-31` headers

2. **Compat routes:** Gradual sunset
   - Mark all compat routes as deprecated
   - Set sunset date for removal

---

## 7) Security Assessment

### Strengths
- ✅ **Centralized cookie management** prevents inconsistencies
- ✅ **HttpOnly cookies** prevent XSS token theft
- ✅ **CSRF protection** via token validation
- ✅ **Token rotation** on refresh
- ✅ **Scope-based authorization** system

### Areas for Improvement
- ⚠️ **Legacy routes** still accessible (should redirect)
- ⚠️ **Multiple backup files** create confusion
- ⚠️ **OAuth cookie handling** not fully centralized

---

## 8) Next Actions

### Immediate (High Priority)
1. **Remove backup files** - Clean up deprecated implementations
2. **Add deprecation headers** - Mark legacy routes for sunset
3. **Centralize OAuth cookies** - Move to unified cookie management

### Short Term (Medium Priority)
1. **Update frontend tests** - Ensure all tests use canonical paths
2. **Documentation update** - Update API docs to reflect canonical routes
3. **Monitoring setup** - Track usage of legacy vs canonical routes

### Long Term (Low Priority)
1. **Legacy route removal** - Sunset deprecated endpoints
2. **Token store optimization** - Consider performance improvements
3. **Auth flow simplification** - Reduce complexity where possible

---

## Appendix: Receipts

### Generated Files
- `_scan.routes.txt` - All FastAPI route decorators
- `_scan.auth_paths.txt` - Auth-specific route patterns
- `_scan.cookies.calls.txt` - Cookie manipulation calls
- `_scan.jwt.calls.txt` - JWT usage outside tokens module
- `_runtime.routes.txt` - Actual mounted routes at runtime
- `_run.curl.*.txt` - Live endpoint testing results
- `_report.cookies.missing.txt` - Cookie flag compliance report

### Tools Created
- `tools/print_routes.py` - Runtime route dumper
- `tools/audit_cookies.py` - Cookie flag auditor
- `tools/decode_jwt.py` - JWT token decoder

---

**Report Status:** ✅ Complete  
**Next Review:** After cleanup actions completed  
**Maintainer:** Development Team
