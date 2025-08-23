# Auth Finish Contract

## Overview

The auth finish endpoint bridges external authentication (Clerk) to internal app cookies. This document defines the contract between frontend and backend.

## Chosen Style: SPA (Single Page Application)

**Decision**: POST → 204 with Set-Cookie, frontend handles navigation

### Backend Contract

**Endpoint**: `POST /v1/auth/finish`

**Request**:
- Method: `POST`
- Headers: Standard CORS headers
- Body: Empty (no body required)
- CSRF: Required when `CSRF_ENABLED=1`

**Response**:
- Status: `204 No Content` (LOCKED CONTRACT: Always returns 204)
- Headers:
  - `Set-Cookie: access_token=<jwt>; HttpOnly; Secure; SameSite=Lax`
  - `Set-Cookie: refresh_token=<jwt>; HttpOnly; Secure; SameSite=Lax`
  - CORS headers as configured

**Behavior**:
1. Verify Clerk session via `require_user_or_dev` dependency
2. Mint new access and refresh tokens (unless valid tokens already exist for user)
3. Set HttpOnly cookies with proper security flags
4. Return 204 (no redirect)
5. **IDEMPOTENT**: Safe to call multiple times - if valid cookies already exist for the user, returns 204 without setting new cookies

### Frontend Contract

**Implementation**: `frontend/src/app/page.tsx`

**Flow**:
1. Detect signed-in state but missing app cookies
2. Call `POST /v1/auth/finish` via `apiFetch`
3. Check for `204` status code
4. On success: call `router.push('/')` for navigation
5. On error: show error message, retry logic

**Code Example**:
```typescript
const res = await apiFetch('/v1/auth/finish', {
  method: 'POST',
  auth: false,
  signal: controller.signal
});

if (res.status === 204) {
  // Success: cookies set by backend, navigate to home
  router.push('/');
} else {
  throw new Error(`Unexpected status: ${res.status}`);
}
```

## Alternative: Redirect Style (Not Used)

**GET /v1/auth/finish → 302 redirect**

- Backend sets cookies and redirects to target URL
- Frontend follows redirect automatically
- Simpler but less control over navigation flow

## Security Considerations

1. **CSRF Protection**: POST requests require CSRF token when enabled
2. **Cookie Security**: HttpOnly, Secure, SameSite flags set appropriately
3. **Session Validation**: Clerk session verified server-side before minting tokens
4. **Token Rotation**: New tokens minted on each finish call (unless idempotent skip)
5. **Idempotency**: Safe to call multiple times without side effects

## Testing

Use the runtime receipts test script:
```bash
bash scripts/test_runtime_receipts.sh
```

This validates:
- Status codes (expect 204 for POST)
- Set-Cookie headers present
- CORS headers configured
- No redirects on POST
- Idempotency (multiple calls return 204)

## Migration Notes

- Legacy GET support maintained for direct browser navigation
- SPA should use POST for consistent behavior
- Frontend handles all navigation after successful auth finish
- **LOCKED CONTRACT**: Endpoint always returns 204 for POST, is idempotent
