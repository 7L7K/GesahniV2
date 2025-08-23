# Cookie Centralization System

## Overview

The cookie centralization system ensures all cookie operations go through a single, consistent interface. This prevents cookie configuration drift, security issues, and maintenance problems.

## Architecture

### 1. `app/cookie_config.py` - Configuration Layer

**Purpose**: Single source of truth for cookie attributes and TTL policy.

**Key Functions**:
- `get_cookie_config(request)` - Computes secure, samesite, domain, path from environment
- `get_token_ttls()` - Returns access/refresh token TTLs from environment
- `format_cookie_header(...)` - Formats Set-Cookie headers with consistent attributes

**Environment Variables**:
- `COOKIE_SECURE` - Force secure cookies (default: auto-detect)
- `COOKIE_SAMESITE` - SameSite attribute (default: "lax")
- `JWT_EXPIRE_MINUTES` - Access token TTL (default: 15)
- `JWT_REFRESH_EXPIRE_MINUTES` - Refresh token TTL (default: 43200)
- `DEV_MODE` - Development mode flag (default: auto-detect)

### 2. `app/cookies.py` - Facade Layer

**Purpose**: The only place that sends Set-Cookie headers.

**Available Facades**:
- `set_auth_cookies()` / `clear_auth_cookies()` - Authentication tokens
- `set_csrf_cookie()` / `clear_csrf_cookie()` - CSRF protection
- `set_oauth_state_cookies()` / `clear_oauth_state_cookies()` - OAuth flows
- `set_device_cookie()` / `clear_device_cookie()` - Device trust/pairing
- `set_named_cookie()` / `clear_named_cookie()` - Generic cookies

## Usage Examples

### Authentication Cookies

```python
from app.cookies import set_auth_cookies, clear_auth_cookies

# Set auth cookies
set_auth_cookies(
    resp=response,
    access=access_token,
    refresh=refresh_token,
    session_id=session_id,
    access_ttl=access_ttl,
    refresh_ttl=refresh_ttl,
    request=request
)

# Clear auth cookies
clear_auth_cookies(resp=response, request=request)
```

### OAuth State Cookies

```python
from app.cookies import set_oauth_state_cookies, clear_oauth_state_cookies

# Set OAuth state cookies
set_oauth_state_cookies(
    resp=response,
    state=oauth_state,
    next_url=redirect_url,
    request=request,
    provider="g"  # For Google OAuth
)

# Clear OAuth state cookies
clear_oauth_state_cookies(resp=response, request=request, provider="g")
```

### CSRF Protection

```python
from app.cookies import set_csrf_cookie, clear_csrf_cookie

# Set CSRF token
set_csrf_cookie(
    resp=response,
    token=csrf_token,
    ttl=3600,  # 1 hour
    request=request
)

# Clear CSRF token
clear_csrf_cookie(resp=response, request=request)
```

### Device Trust Cookies

```python
from app.cookies import set_device_cookie, clear_device_cookie

# Set device trust cookie
set_device_cookie(
    resp=response,
    value=device_trust_value,
    ttl=86400,  # 24 hours
    request=request
)

# Clear device trust cookie
clear_device_cookie(resp=response, request=request)
```

## Cookie Attributes

All cookies use consistent attributes from centralized configuration:

- **Host-only**: No Domain attribute (better security)
- **Path**: `/` (site-wide)
- **SameSite**: Configurable (default: "lax")
- **HttpOnly**: True for auth/state cookies, False for client-accessible
- **Secure**: Auto-detected based on environment
- **Priority**: High for critical auth cookies

## Session Management

The `__session` cookie is always an opaque session ID (never a JWT) and follows the access token TTL for consistent lifecycle management.

## Enforcement

### Test Guards

The system includes automated tests to prevent violations:

- `tests/unit/test_cookie_guard.py` - Prevents raw `set_cookie()` calls
- `test_cookie_centralization.py` - Validates facade usage

### Allowed Files

Only these files can contain direct cookie operations:
- `app/cookies.py` - The centralized facade
- `app/cookie_config.py` - Configuration utilities
- `tests/unit/test_cookie_guard.py` - The guard test itself

## Migration Guide

### Before (Deprecated)

```python
# ❌ Don't do this
response.set_cookie(
    "access_token",
    token,
    httponly=True,
    secure=secure,
    samesite=samesite,
    max_age=ttl,
    path="/"
)
```

### After (Required)

```python
# ✅ Do this
from app.cookies import set_auth_cookies

set_auth_cookies(
    resp=response,
    access=token,
    refresh=refresh_token,
    session_id=session_id,
    access_ttl=ttl,
    refresh_ttl=refresh_ttl,
    request=request
)
```

## Best Practices

1. **Always use facades**: Never call `response.set_cookie()` directly
2. **Pass request object**: Required for proper configuration
3. **Use appropriate TTLs**: Let the system handle TTL alignment
4. **Clear cookies properly**: Use clear functions with Max-Age=0
5. **Test cookie behavior**: Use the provided test helpers

## Troubleshooting

### Common Issues

1. **Missing request parameter**: All facade functions require the request object
2. **Incorrect TTLs**: Use `get_token_ttls()` for consistent token lifetimes
3. **Cookie not clearing**: Ensure you're using the clear functions, not setting empty values

### Debugging

Enable debug logging to see cookie operations:

```bash
export LOG_LEVEL=DEBUG
```

### Testing

Run the cookie tests to verify compliance:

```bash
python -m pytest tests/unit/test_cookie_guard.py -v
python test_cookie_centralization.py
```

## Security Considerations

- **HttpOnly**: Auth and state cookies are HttpOnly by default
- **Secure**: Automatically enabled in production HTTPS environments
- **SameSite**: Configurable for cross-site scenarios
- **Host-only**: No Domain attribute prevents subdomain issues
- **Priority**: Critical auth cookies use Priority=High

## Environment Configuration

### Development

```bash
export DEV_MODE=1
export COOKIE_SECURE=0
export COOKIE_SAMESITE=lax
```

### Production

```bash
export COOKIE_SECURE=1
export COOKIE_SAMESITE=lax
export JWT_EXPIRE_MINUTES=15
export JWT_REFRESH_EXPIRE_MINUTES=43200
```

### Cross-Site Scenarios

```bash
export COOKIE_SAMESITE=none
export COOKIE_SECURE=1  # Required when SameSite=None
```
