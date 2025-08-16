# CSRF Policy

## Overview

This application uses a double-submit CSRF protection mechanism for cookie-based authentication.

## Policy

**When CSRF_ENABLED=1:**
- All mutating requests (POST/PUT/PATCH/DELETE) require CSRF token
- Safe methods (GET/HEAD/OPTIONS) are exempt
- Double-submit pattern: `X-CSRF-Token` header must match `csrf_token` cookie

**When CSRF_ENABLED=0:**
- No CSRF protection (rely on SameSite cookie rules)
- All methods allowed

## Implementation

### Backend (FastAPI)

**Middleware**: `app/csrf.py`

- **Double-submit**: Header `X-CSRF-Token` must match cookie `csrf_token`
- **Legacy support**: `X-CSRF` header supported when `CSRF_LEGACY_GRACE=1`
- **OAuth exemptions**: Apple/Google callback endpoints exempted
- **Safe methods**: GET/HEAD/OPTIONS bypass CSRF checks

**Configuration**:
```bash
# Enable CSRF protection
CSRF_ENABLED=1

# Allow legacy X-CSRF header (deprecated, removal 2025-12-31)
CSRF_LEGACY_GRACE=1
```

### Frontend (Next.js)

**Token Management**:
- CSRF token stored in `csrf_token` cookie
- Token included in `X-CSRF-Token` header for all mutating requests
- Automatic token refresh on 403 responses

**API Client**:
```typescript
// apiFetch automatically includes CSRF token for POST/PUT/PATCH/DELETE
await apiFetch('/v1/mutate', { method: 'POST', body: data });
```

## Security Considerations

1. **Cookie Auth Only**: CSRF protection only applies when using cookie-based authentication
2. **Bearer Token**: No CSRF required for `Authorization: Bearer` requests
3. **SameSite Rules**: When CSRF disabled, rely on `SameSite=Lax/Strict` cookie rules
4. **OAuth Callbacks**: Provider callbacks use state/nonce validation instead

## Testing

Test CSRF protection:
```bash
# Should fail without CSRF token
curl -X POST http://127.0.0.1:8000/v1/auth/logout

# Should succeed with CSRF token
curl -X POST http://127.0.0.1:8000/v1/auth/logout \
  -H "X-CSRF-Token: $(curl -s http://127.0.0.1:8000/v1/csrf | jq -r .token)" \
  -b "csrf_token=$(curl -s http://127.0.0.1:8000/v1/csrf | jq -r .token)"
```

## Migration Notes

- CSRF disabled by default (`CSRF_ENABLED=0`)
- Enable for production cookie-based auth
- Legacy `X-CSRF` header deprecated, removal scheduled 2025-12-31
- OAuth flows exempted due to state/nonce validation
