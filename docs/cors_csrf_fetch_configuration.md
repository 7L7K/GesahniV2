# CORS / CSRF / Fetch Configuration

This document describes the implementation of CORS, CSRF, and fetch configuration for the Gesahni application.

## Overview

The application implements a secure cross-origin configuration with:
- **Backend CORS**: Properly configured to allow `http://localhost:3000` with credentials
- **Frontend Fetch**: All API calls use `credentials: 'include'` by default
- **CSRF Protection**: Double-submit pattern with route-scoped bypass for OAuth callbacks

## Backend CORS Configuration

### Environment Variables

```bash
# CORS configuration
CORS_ALLOW_ORIGINS=http://localhost:3000
CORS_ALLOW_CREDENTIALS=true
```

### Implementation

The CORS middleware is configured in `app/main.py` (lines 1572-1582):

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # ["http://localhost:3000"]
    allow_credentials=allow_credentials,  # True
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],  # Only necessary headers exposed
    max_age=600,
)
```

### Headers

The backend sends the following CORS headers:

- `Access-Control-Allow-Origin: http://localhost:3000`
- `Access-Control-Allow-Credentials: true`
- `Vary: Origin` (handled by FastAPI's CORSMiddleware)

### Security Features

1. **Single Origin**: Only `http://localhost:3000` is allowed (not `127.0.0.1:3000`)
2. **Credentials Required**: Cookies and authentication headers are allowed
3. **Minimal Header Exposure**: Only `X-Request-ID` is exposed to the frontend
4. **Preflight Caching**: 10-minute cache for preflight requests

## Frontend Fetch Configuration

### Default Credentials

All API calls use `credentials: 'include'` by default in `frontend/src/lib/api.ts`:

```typescript
const { auth = true, headers, dedupe = true, shortCacheMs, contextKey, credentials = 'include', ...rest } = init as any;
```

### Implementation Details

1. **apiFetch Function**: Centralized fetch wrapper that includes credentials
2. **Refresh Requests**: All authentication refresh calls include credentials
3. **WebSocket Connections**: WebSocket connections also include credentials
4. **Error Handling**: Proper error handling for authentication failures

### Example Usage

```typescript
// All these calls automatically include credentials: 'include'
await apiFetch('/v1/whoami');
await apiFetch('/v1/profile', { method: 'POST', body: JSON.stringify(data) });
await refreshAuth();
```

## CSRF Protection

### Environment Variables

```bash
# CSRF protection: 0=disabled (development), 1=enabled (production)
CSRF_ENABLED=0
```

### Implementation

CSRF protection is implemented in `app/csrf.py`:

1. **Double-Submit Pattern**: Requires both `X-CSRF-Token` header and `csrf_token` cookie
2. **Route-Scoped Bypass**: OAuth callbacks bypass CSRF protection
3. **Safe Methods**: GET, HEAD, OPTIONS requests are not protected
4. **Cross-Site Support**: Handles cross-site scenarios when `COOKIE_SAMESITE=none`

### CSRF Token Flow

1. **Token Generation**: Server generates CSRF token via `/v1/csrf` endpoint
2. **Cookie Setting**: Token is set as `csrf_token` cookie
3. **Header Inclusion**: Frontend includes token in `X-CSRF-Token` header
4. **Validation**: Server validates header matches cookie

### OAuth Callback Bypass

The following routes bypass CSRF protection:
- `/v1/auth/apple/callback`
- `/auth/apple/callback`

This is necessary because OAuth providers cannot include CSRF tokens.

### Cross-Site CSRF Handling

When `COOKIE_SAMESITE=none` is configured:
- CSRF validation accepts tokens from header only
- Additional security measures can be implemented
- Requires `X-Auth-Intent` header for sensitive operations

## Security Considerations

### CORS Security

1. **Origin Validation**: Only `http://localhost:3000` is allowed
2. **No Wildcard Origins**: Prevents broad access
3. **Credentials Required**: Ensures authentication works properly
4. **Minimal Header Exposure**: Reduces attack surface

### CSRF Security

1. **Double-Submit**: Prevents token theft attacks
2. **Route Bypass**: Only for OAuth callbacks with explicit validation
3. **Safe Methods**: GET requests cannot modify state
4. **Cross-Site Support**: Handles SameSite=None scenarios

### Fetch Security

1. **Credentials Always**: Ensures cookies are sent with requests
2. **Error Handling**: Proper handling of authentication failures
3. **Token Management**: Automatic CSRF token inclusion
4. **Refresh Logic**: Automatic token refresh on 401 errors

## Testing

### Integration Tests

The configuration is verified by `tests/integration/test_cors_csrf_fetch_integration.py`:

1. **CORS Headers**: Verifies proper CORS headers are set
2. **Origin Validation**: Tests that only allowed origins work
3. **CSRF Protection**: Tests CSRF token validation
4. **OAuth Bypass**: Verifies OAuth callbacks bypass CSRF
5. **Environment Variables**: Ensures configuration is documented

### Manual Testing

```bash
# Test CORS preflight
curl -X OPTIONS http://localhost:8000/v1/whoami \
  -H "Origin: http://localhost:3000" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: content-type,x-csrf-token"

# Test CSRF protection (when enabled)
CSRF_ENABLED=1 curl -X POST http://localhost:8000/v1/profile \
  -H "Content-Type: application/json" \
  -d '{"name": "test"}'
```

## Environment Configuration

### Development

```bash
# Development environment
CORS_ALLOW_ORIGINS=http://localhost:3000
CORS_ALLOW_CREDENTIALS=true
CSRF_ENABLED=0  # Disabled for development
COOKIE_SECURE=0
COOKIE_SAMESITE=lax
```

### Production

```bash
# Production environment
CORS_ALLOW_ORIGINS=https://app.gesahni.com
CORS_ALLOW_CREDENTIALS=true
CSRF_ENABLED=1  # Enabled for production
COOKIE_SECURE=1
COOKIE_SAMESITE=strict
```

## Troubleshooting

### Common Issues

1. **CORS Errors**: Ensure `CORS_ALLOW_ORIGINS` is set to exactly `http://localhost:3000`
2. **CSRF Errors**: Check that `CSRF_ENABLED` is set appropriately for your environment
3. **Cookie Issues**: Verify `COOKIE_SECURE` and `COOKIE_SAMESITE` settings
4. **Fetch Errors**: Ensure all API calls use `credentials: 'include'`

### Debug Commands

```bash
# Check CORS configuration
grep -E "(CORS_ALLOW|CSRF_ENABLED)" .env

# Test CORS headers
curl -I -X OPTIONS http://localhost:8000/v1/whoami \
  -H "Origin: http://localhost:3000"

# Test CSRF protection
CSRF_ENABLED=1 curl -X POST http://localhost:8000/v1/csrf
```

## References

- [FastAPI CORS Documentation](https://fastapi.tiangolo.com/tutorial/cors/)
- [CSRF Protection Best Practices](https://owasp.org/www-community/attacks/csrf)
- [Fetch API Credentials](https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API/Using_Fetch#sending_a_request_with_credentials_included)
