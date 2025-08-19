# Deny Path Logging Implementation

## Overview

We have successfully implemented explicit logging for all deny paths in the authentication system. Each deny path now logs a single, explicit reason with relevant context to help with debugging authentication issues.

## Implemented Deny Paths

### 1. CSRF Middleware (`app/csrf.py`)

**Deny Paths:**
- `deny: csrf_legacy_header_disabled header=<...>` - When legacy X-CSRF header is used but not allowed
- `deny: csrf_missing_header header=<...> cookie=<...>` - When CSRF header or cookie is missing
- `deny: csrf_mismatch header=<...> cookie=<...>` - When CSRF header doesn't match cookie

**Example Log:**
```
deny: csrf_missing_header header=<None> cookie=<None>
```

### 2. Scope Validation (`app/deps/scopes.py`)

**Deny Paths:**
- `deny: missing_scope scope=<...> available=<...>` - When required scope is not available
- `deny: missing_scope scopes=<...> reason=no_payload` - When JWT payload is missing

**Example Log:**
```
deny: missing_scope scope=<admin:write> available=<admin:read>
```

### 3. Token Verification (`app/security.py`)

**Deny Paths:**
- `deny: missing_jwt_secret` - When JWT_SECRET is not configured
- `deny: missing_token` - When no token is provided
- `deny: token_expired` - When token has expired
- `deny: invalid_token` - When token is invalid
- `deny: missing_token_strict` - When strict mode requires header token
- `deny: invalid_token_strict` - When strict mode token is invalid

**Example Logs:**
```
deny: missing_token
deny: token_expired
deny: invalid_token
```

### 4. Rate Limiting (`app/security.py`)

**Deny Paths:**
- `deny: rate_limit_exceeded key=<...> limit=<...> window=<...> retry_after=<...>` - When long-term rate limit is exceeded
- `deny: rate_limit_burst_exceeded key=<...> limit=<...> window=<...> retry_after=<...>` - When burst rate limit is exceeded

**Example Log:**
```
deny: rate_limit_exceeded key=<user123> limit=<60> window=<60.0s> retry_after=<45s>
```

### 5. WebSocket Origin Validation (`app/security.py`)

**Deny Paths:**
- `deny: origin_not_allowed origin=<...>` - When WebSocket origin is not allowed

**Example Log:**
```
deny: origin_not_allowed origin=<http://evil.com>
```

## Testing the Implementation

### Manual Testing

1. **CSRF Testing:**
   ```bash
   # Enable CSRF and test missing header
   CSRF_ENABLED=1 curl -X POST http://localhost:8000/v1/profile \
     -H 'Content-Type: application/json' \
     -d '{"test": "data"}'
   ```

2. **Token Testing:**
   ```bash
   # Test missing token
   curl -X POST http://localhost:8000/v1/ask \
     -H 'Content-Type: application/json' \
     -d '{"question": "test"}'
   ```

3. **Scope Testing:**
   ```bash
   # Test missing scope (requires token with insufficient scopes)
   curl -X POST http://localhost:8000/v1/admin/config \
     -H 'Authorization: Bearer <token_with_admin_read>'
   ```

4. **Rate Limiting Testing:**
   ```bash
   # Test rate limiting by making many requests
   for i in {1..100}; do
     curl -X POST http://localhost:8000/v1/ask \
       -H 'Content-Type: application/json' \
       -d '{"question": "test"}'
   done
   ```

5. **WebSocket Origin Testing:**
   ```bash
   # Test WebSocket origin validation
   curl -H 'Origin: http://evil.com' http://localhost:8000/v1/ws/music
   ```

### Automated Testing

Use the provided test script:
```bash
./test_deny_paths.sh
```

## Log Format

All deny path logs follow this format:
```
deny: <reason> <context>
```

Where:
- `deny:` - Prefix to identify deny path logs
- `<reason>` - Specific reason for denial
- `<context>` - Relevant context (tokens, scopes, limits, etc.)

## Benefits

1. **Quick Debugging:** Clear identification of why requests are being denied
2. **Security Monitoring:** Easy to track and monitor authentication failures
3. **Operational Visibility:** Clear logs for operations teams
4. **Development Support:** Helps developers understand authentication issues

## Configuration

The logging level can be controlled via the `LOG_LEVEL` environment variable:
```bash
LOG_LEVEL=DEBUG python -m uvicorn app.main:app --reload
```

## Files Modified

1. `app/csrf.py` - Added CSRF deny path logging
2. `app/deps/scopes.py` - Added scope validation deny path logging  
3. `app/security.py` - Added token verification, rate limiting, and WebSocket origin deny path logging

## Next Steps

1. **Monitor Logs:** Watch for deny path patterns in production
2. **Alert on Patterns:** Set up alerts for unusual deny path patterns
3. **Metrics:** Consider adding metrics for deny path frequencies
4. **Documentation:** Update API documentation to reference these log messages
