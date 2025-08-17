# Middleware & Redirect Best Practices Implementation

This document outlines the implementation of middleware and redirect best practices to avoid hardcoded URLs and ensure consistent URL handling across the application.

## Overview

The following best practices have been implemented:

1. **Middleware & redirects**: Never hardcode `http://…:3000`. Build from `req.nextUrl`
2. **Clerk/Auth**: Use relative paths for `signInUrl`, `signUpUrl`, `afterSignInUrl`, etc.
3. **CORS/CSRF**: Set exactly one front-end origin in allowlists
4. **Cookies**: Don't set `Domain=` for dev; let `host=exact match`. One host = one cookie jar
5. **WS URLs**: Derive from the same `APP_URL`/helper every time

## Implementation Details

### 1. Frontend URL Helpers (`frontend/src/lib/urls.ts`)

Created centralized URL utilities for building URLs from request context:

- `buildUrlFromRequest()` - Build URLs from request's nextUrl
- `buildRedirectUrl()` - Build redirect URLs from request context
- `getBaseUrl()` - Extract base URL from request
- `buildAuthUrl()` - Build relative auth URLs for Clerk
- `buildWebSocketUrl()` - Build WebSocket URLs from API origin
- `sanitizeNextPath()` - Sanitize next parameters to prevent open redirects

### 2. Backend URL Helpers (`app/url_helpers.py`)

Created centralized URL utilities for the backend:

- `get_app_url()` - Get base URL for the application
- `get_frontend_url()` - Get frontend URL from CORS configuration
- `build_ws_url()` - Build WebSocket URLs from base URL
- `build_api_url()` - Build API URLs from base URL
- `is_dev_environment()` - Check if in development environment

### 3. Middleware Updates (`frontend/src/middleware.ts`)

Updated middleware to use URL helpers instead of hardcoded URLs:

- Removed hardcoded `127.0.0.1` hostname assignments
- Use `buildRedirectUrl()` for all redirects
- Use `sanitizeNextPath()` for next parameter validation
- Import URL helpers from centralized module

### 4. Clerk Auth Pages

Updated Clerk auth pages to use relative paths:

- `frontend/src/app/sign-in/[[...sign-in]]/page.tsx`
- `frontend/src/app/sign-up/[[...sign-up]]/page.tsx`
- Use `buildAuthUrl()` for `afterSignInUrl` and `afterSignUpUrl`

### 5. CORS Configuration

Updated CORS configuration to use single origin:

- `env.example`: Changed from multiple origins to single origin
- `app/main.py`: Added validation to ensure only one origin is used
- WebSocket endpoints: Updated to use single origin approach
- Added warning logs for multiple origins detected

### 6. Cookie Configuration

Enhanced cookie configuration:

- `app/cookie_config.py`: Explicitly set `domain=None` for host-only cookies
- Added comment: "Explicitly no domain for host-only cookies (one host = one cookie jar)"
- Ensures consistent cookie behavior across environments

### 7. WebSocket URL Building

Updated WebSocket URL generation:

- `frontend/src/lib/api.ts`: Use `buildWebSocketUrl()` helper
- `app/main.py`: Use `build_ws_url()` for debug page
- Consistent URL derivation from API origin

### 8. CSP Configuration

Updated Content Security Policy:

- `frontend/src/lib/csp.ts`: Use centralized URL helpers
- Build WebSocket URLs dynamically from API origin
- Consistent URL generation across environments

## Environment Configuration

### Frontend Environment Variables

```env
# API origin for backend communication
NEXT_PUBLIC_API_ORIGIN=http://127.0.0.1:8000

# Clerk configuration (relative paths)
NEXT_PUBLIC_CLERK_SIGN_IN_URL=/sign-in
NEXT_PUBLIC_CLERK_SIGN_UP_URL=/sign-up
```

### Backend Environment Variables

```env
# Single frontend origin for CORS
CORS_ALLOW_ORIGINS=http://localhost:3000

# Cookie configuration (no domain for dev)
COOKIE_SECURE=0
COOKIE_SAMESITE=lax
DEV_MODE=1

# Optional: explicit app URL
APP_URL=http://127.0.0.1:8000
```

## Security Benefits

1. **Open Redirect Prevention**: `sanitizeNextPath()` prevents open redirects by rejecting absolute URLs
2. **CORS Security**: Single origin configuration reduces attack surface
3. **Cookie Security**: Host-only cookies prevent cross-subdomain attacks
4. **URL Consistency**: Centralized URL building prevents inconsistencies

## Testing

### Frontend Tests

- `frontend/src/lib/__tests__/urls.test.ts`: Comprehensive tests for URL helper functions
- Tests cover URL building, sanitization, and edge cases
- 18 test cases covering all helper functions

### Backend Tests

- `tests/unit/test_url_helpers.py`: Comprehensive tests for backend URL helpers
- Tests cover environment variable handling and URL building
- 22 test cases covering all helper functions

## Migration Guide

### For Developers

1. **Use URL helpers**: Replace hardcoded URLs with helper functions
2. **Middleware redirects**: Use `buildRedirectUrl()` instead of manual URL construction
3. **Auth URLs**: Use `buildAuthUrl()` for Clerk configuration
4. **WebSocket URLs**: Use `buildWebSocketUrl()` for consistent URL generation

### For Deployment

1. **Environment variables**: Set `CORS_ALLOW_ORIGINS` to single origin
2. **Cookie configuration**: Ensure `domain=None` for host-only cookies
3. **URL consistency**: Use `APP_URL` for explicit backend URL configuration

## Best Practices Summary

✅ **Never hardcode URLs** - Use centralized helpers
✅ **Build from request context** - Use `req.nextUrl` for redirects
✅ **Use relative paths** - For auth endpoints and internal redirects
✅ **Single CORS origin** - Reduce attack surface
✅ **Host-only cookies** - One host = one cookie jar
✅ **Consistent URL derivation** - Same helper for all URL types
✅ **Open redirect prevention** - Sanitize all user inputs
✅ **Environment-based configuration** - No hardcoded values

## Files Modified

### Frontend
- `frontend/src/lib/urls.ts` (new)
- `frontend/src/lib/__tests__/urls.test.ts` (new)
- `frontend/src/middleware.ts`
- `frontend/src/app/sign-in/[[...sign-in]]/page.tsx`
- `frontend/src/app/sign-up/[[...sign-up]]/page.tsx`
- `frontend/src/lib/api.ts`
- `frontend/src/lib/csp.ts`

### Backend
- `app/url_helpers.py` (new)
- `tests/unit/test_url_helpers.py` (new)
- `app/main.py`
- `app/api/care_ws.py`
- `app/api/music.py`
- `app/cookie_config.py`
- `env.example`

This implementation ensures consistent, secure, and maintainable URL handling across the entire application while following industry best practices for middleware and redirects.
