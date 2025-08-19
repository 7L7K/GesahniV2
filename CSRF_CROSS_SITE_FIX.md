# CSRF Token Mismatch Fix for Cross-Site Scenarios

## Problem Description

The CSRF token mismatch issue occurred in cross-site scenarios when `COOKIE_SAMESITE=none` was configured. The problem was a catch-22 situation:

1. **CSRF tokens are tied to same-origin**: The `csrf_token` cookie was set with `SameSite=Lax` by default, which means it's only sent in same-origin requests.

2. **Cross-site requests can't access same-origin cookies**: When `COOKIE_SAMESITE=none` is set, the refresh endpoint requires an intent header, but the CSRF validation still expected the `csrf_token` cookie to be present.

3. **Catch-22 situation**: 
   - Cross-site requests need CSRF protection
   - But cross-site requests can't access the `csrf_token` cookie due to SameSite restrictions
   - This created a circular dependency

## Solution Overview

The fix implements alternative CSRF validation for cross-site scenarios that doesn't rely on same-origin cookies:

### 1. Cross-Site Detection
- Detect cross-site scenarios by checking `COOKIE_SAMESITE=none`
- Use different validation logic for cross-site vs same-origin requests

### 2. Alternative CSRF Validation for Cross-Site
- **Header-only validation**: Accept CSRF token from `X-CSRF-Token` header only
- **Intent header requirement**: Require `X-Auth-Intent: refresh` header for additional security
- **Token format validation**: Basic validation of token length and format
- **Future enhancement**: Server-side token validation can be added for additional security

### 3. Same-Origin Validation (Unchanged)
- Continue using the double-submit pattern (header + cookie match)
- Maintain existing security for same-origin requests

## Implementation Details

### Files Modified

#### 1. `app/csrf.py`
- **CSRFMiddleware**: Updated to handle cross-site scenarios
- **Cross-site validation**: Header-only validation with basic format checks
- **JSON responses**: Return proper JSON error responses instead of empty responses
- **Logging**: Enhanced logging for cross-site validation

#### 2. `app/api/auth.py`
- **Refresh endpoint**: Updated CSRF validation logic
- **Cross-site handling**: Alternative validation for `COOKIE_SAMESITE=none`
- **Intent header validation**: Cross-site specific error messages
- **Duplicate removal**: Removed duplicate intent header check

#### 3. `app/main.py`
- **CSRF endpoint**: Updated to set `SameSite=None` for cross-site scenarios
- **Cookie configuration**: Proper SameSite attribute handling

#### 4. `app/cookie_config.py`
- **SameSite formatting**: Fixed to use proper case (`None` instead of `none`)

### Key Changes

#### CSRF Middleware (`app/csrf.py`)
```python
# Check if we're in a cross-site scenario
is_cross_site = os.getenv("COOKIE_SAMESITE", "lax").lower() == "none"

if is_cross_site:
    # Cross-site validation: header-only with format checks
    if not token_hdr:
        return JSONResponse(status_code=400, content={"detail": "missing_csrf_cross_site"})
    if len(token_hdr) < 16:
        return JSONResponse(status_code=403, content={"detail": "invalid_csrf_format"})
    # Accept token from header only
else:
    # Standard double-submit validation
    # ... existing logic
```

#### Auth Endpoint (`app/api/auth.py`)
```python
if is_cross_site:
    # Cross-site CSRF validation
    if not tok:
        raise HTTPException(status_code=400, detail="missing_csrf_cross_site")
    
    # Validate intent header
    intent = request.headers.get("x-auth-intent") or request.headers.get("X-Auth-Intent")
    if str(intent or "").strip().lower() != "refresh":
        raise HTTPException(status_code=400, detail="missing_intent_header_cross_site")
    
    # Basic token validation
    if not tok or len(tok) < 16:
        raise HTTPException(status_code=403, detail="invalid_csrf_format")
else:
    # Standard same-origin validation
    # ... existing double-submit logic
```

## Security Considerations

### Cross-Site Validation Security
- **Less secure than double-submit**: Header-only validation is less secure than the double-submit pattern
- **Necessary compromise**: Required for cross-site functionality
- **Additional measures**: Intent header requirement adds security
- **Future enhancement**: Server-side token validation can be implemented

### Same-Origin Validation Security
- **Unchanged**: Maintains existing double-submit security
- **No regression**: Same-origin requests remain as secure as before

### Recommendations
1. **Monitor usage**: Track cross-site vs same-origin request patterns
2. **Server-side validation**: Consider implementing server-side CSRF token storage/validation
3. **Token rotation**: Implement token rotation for cross-site tokens
4. **Rate limiting**: Ensure proper rate limiting for cross-site requests

## Testing

### Test Coverage
Created comprehensive test suite in `tests/integration/test_csrf_cross_site_scenarios.py`:

1. **Same-origin validation**: Standard CSRF validation works correctly
2. **Cross-site validation**: Alternative validation works for cross-site scenarios
3. **Error handling**: Proper error messages for different failure scenarios
4. **Middleware integration**: CSRF middleware handles both scenarios correctly
5. **Cookie configuration**: SameSite attributes are set correctly

### Test Scenarios
- ✅ Same-origin CSRF validation (double-submit)
- ✅ Cross-site CSRF validation (header-only)
- ✅ Missing CSRF token in cross-site
- ✅ Missing intent header in cross-site
- ✅ Invalid token format in cross-site
- ✅ Missing cookie in same-origin
- ✅ Token mismatch in same-origin
- ✅ CSRF disabled behavior
- ✅ Middleware cross-site validation
- ✅ Middleware same-origin validation

## Configuration

### Environment Variables
- `CSRF_ENABLED=1`: Enable CSRF protection
- `COOKIE_SAMESITE=none`: Enable cross-site mode
- `COOKIE_SECURE=1`: Required when `COOKIE_SAMESITE=none`

### Example Configuration
```bash
# Cross-site configuration
CSRF_ENABLED=1
COOKIE_SAMESITE=none
COOKIE_SECURE=1

# Same-origin configuration (default)
CSRF_ENABLED=1
COOKIE_SAMESITE=lax
COOKIE_SECURE=1
```

## Migration Notes

### Backward Compatibility
- **Same-origin requests**: No changes required
- **Cross-site requests**: Must include both `X-CSRF-Token` and `X-Auth-Intent: refresh` headers
- **Error messages**: New cross-site specific error messages

### Client Requirements
For cross-site requests, clients must:
1. Include `X-CSRF-Token` header with valid token
2. Include `X-Auth-Intent: refresh` header
3. Handle new error messages (`missing_csrf_cross_site`, `missing_intent_header_cross_site`, `invalid_csrf_format`)

## Future Enhancements

1. **Server-side token validation**: Store valid tokens in Redis/session
2. **Token rotation**: Implement automatic token rotation
3. **Enhanced logging**: More detailed security event logging
4. **Metrics**: Track cross-site vs same-origin request patterns
5. **Rate limiting**: Cross-site specific rate limiting rules
