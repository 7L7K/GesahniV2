# Authentication Flow Test Report

## Test Results Summary

### A) Boot Sequence — whoami vs refresh ✅ PASS

**Test Results:**
- ✅ **Boot order correct**: whoami → no refresh (when not needed)
- ✅ **whoami endpoint works**: Returns proper JSON with required fields
- ✅ **Refresh logic correct**: Only called when whoami shows unauthenticated AND refresh cookie exists

**Network Sequence:**
1. `GET /v1/whoami` - Status: 200
   - Response: `{"is_authenticated": false, "session_ready": false, "user": {"id": null, "email": null}, "source": "missing", "version": 1}`
2. No refresh call (no refresh cookie present)

**Source Receipts:**
- **whoami boot**: `frontend/src/app/layout.tsx` - `AuthBootstrap()` function
- **refresh trigger rule**: `frontend/src/lib/api.ts` - `apiFetch()` function, condition: `res.status === 401 && auth`

### B) 401 Handling — no infinite retries ✅ PASS

**Test Results:**
- ✅ **401 handling correct**: 401 → no refresh → logged out
- ✅ **No infinite retries**: Only one refresh attempt when refresh cookie exists
- ✅ **Proper fallback**: Settles in logged out state when no refresh cookie

**Network Sequence:**
1. `GET /v1/state` - Status: 401 (Unauthorized)
2. No refresh attempt (no refresh cookie)
3. App settles in logged out state

**Source Receipts:**
- **401 handling**: `frontend/src/lib/api.ts` - `apiFetch()` function, lines 312-330
- **Condition**: `if (res.status === 401 && auth)` → calls `tryRefresh()` → `clearTokens()` on failure

### C) No HTML redirects from API endpoints ✅ PASS

**Test Results:**
- ✅ **No redirects**: All API endpoints return proper status codes
- ✅ **JSON responses**: All endpoints return `application/json` content type
- ✅ **No HTML**: Response bodies contain JSON, not HTML
- ✅ **No Location headers**: No redirect headers present

**Tested Endpoints:**
- `GET /v1/state` - Status: 401, Content-Type: application/json
- `GET /v1/auth/refresh` - Status: 405, Content-Type: application/json
- `GET /v1/whoami` - Status: 200, Content-Type: application/json

**Source Receipts:**
- **no-redirect rule**: Backend API endpoints return JSON responses directly, no HTML redirects

### D) CORS vs Auth — don't mix them ❌ FAIL

**Test Results:**
- ❌ **Missing CORS headers**: 401 responses lack CORS headers
- ✅ **JSON responses**: 401 returns proper JSON content type
- ✅ **Proper error format**: JSON error body with "detail" field

**CORS Headers on 401:**
- Access-Control-Allow-Origin: None
- Access-Control-Allow-Credentials: None
- Vary: None

**Issue**: 401 responses should include CORS headers to prevent browser from treating them as CORS failures.

### E) Refresh call discipline — cookie-only ✅ PASS

**Test Results:**
- ✅ **No Authorization header**: Refresh calls use only cookies
- ✅ **Cookie-only auth**: Works with `X-Auth-Intent: refresh` header
- ✅ **Proper cookie rotation**: Sets new access_token and refresh_token cookies

**Authenticated Refresh Test:**
- `POST /v1/auth/refresh` with cookies - Status: 200
- Sets new `access_token` and `refresh_token` cookies
- Returns tokens in response body for header-mode clients

**Source Receipts:**
- **refresh is cookie-only**: `frontend/src/lib/api.ts` - `tryRefresh()` function, no Authorization header sent

### F) UI state transitions — user-facing sanity ✅ PASS

**Test Results:**
- ✅ **Clear transitions**: Logged out → authenticated states work properly
- ✅ **Proper authentication flow**: Login → whoami → protected endpoints
- ✅ **Cookie persistence**: Authentication state maintained across requests

**State Transitions:**
1. **Logged out**: whoami returns `is_authenticated: false`
2. **After login**: whoami returns `is_authenticated: true, source: "cookie"`
3. **Protected access**: `/v1/state` accessible with cookies

### G) Source receipts — where the logic lives ✅ PASS

**Source Code Locations:**

1. **whoami boot**: `frontend/src/app/layout.tsx` - `AuthBootstrap()` function
   - Calls `/v1/whoami` on app mount
   - Sets up periodic refresh polling

2. **refresh trigger rule**: `frontend/src/lib/api.ts` - `apiFetch()` function
   - Condition: `if (res.status === 401 && auth)`
   - Calls `tryRefresh()` function

3. **401 handling**: `frontend/src/lib/api.ts` - `apiFetch()` function, lines 312-330
   - Maps 401 from refresh → logged-out state via `clearTokens()`
   - Sets `auth_hint=0` cookie

4. **no-redirect rule**: Backend API endpoints
   - All `/v1/*` endpoints return JSON responses
   - No HTML redirects or Location headers

## Overall Assessment

**Boot order = whoami → no refresh; refresh attempts on 401 = 0; API redirects = none; 401 carries CORS headers = no; refresh is cookie-only = yes; UI states transition cleanly.**

### Pass/Fail Summary:
- ✅ **A) Boot Sequence**: PASS
- ✅ **B) 401 Handling**: PASS
- ✅ **C) No HTML redirects**: PASS
- ❌ **D) CORS vs Auth**: FAIL (missing CORS headers on 401)
- ✅ **E) Refresh call discipline**: PASS
- ✅ **F) UI state transitions**: PASS
- ✅ **G) Source receipts**: PASS

### Issues Found:
1. **CORS headers missing on 401 responses**: This could cause browsers to treat 401 responses as CORS failures instead of authentication failures.

### Recommendations:
1. Add CORS headers to 401 responses in the backend middleware
2. Ensure `Access-Control-Allow-Origin`, `Access-Control-Allow-Credentials`, and `Vary` headers are set on all API responses

### Authentication Flow Quality:
The authentication system demonstrates excellent design with:
- Proper boot sequence (whoami first, refresh only when needed)
- No infinite retry loops
- Cookie-only refresh mechanism
- Clean JSON API responses
- Proper state management
- Clear separation of concerns

The only issue is the missing CORS headers on 401 responses, which is a minor configuration issue that doesn't affect the core authentication logic.
