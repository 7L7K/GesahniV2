# OAuth Structured Logging Implementation

## Overview

This document describes the implementation of structured logging for OAuth authentication flows as requested. The implementation adds specific logging patterns for OAuth login URLs, callbacks, and authentication checks.

## Implemented Logging Patterns

### 1. OAuth Login URL Logging (`oauth.login_url`)

**Location**: `app/api/google_oauth.py` - `google_login_url()` function

**Log Level**: INFO

**Message**: `"oauth.login_url"`

**Required Fields**:
- `state_set`: boolean - Whether the OAuth state was successfully set
- `next`: string - The redirect URL after successful authentication
- `cookie_http_only`: boolean - Always `true` for security
- `samesite`: string - Cookie SameSite attribute (always `"Lax"`)

**Example Log**:
```json
{
  "timestamp": "2025-08-21T14:46:01Z",
  "req_id": "9b3e1a10-d45f-40b6-afc7-e4525bfe38db",
  "level": "INFO",
  "component": "app.api.google_oauth",
  "msg": "oauth.login_url",
  "meta": {
    "req_id": "9b3e1a10-d45f-40b6-afc7-e4525bfe38db",
    "component": "google_oauth",
    "msg": "oauth.login_url",
    "state_set": true,
    "next": "/",
    "cookie_http_only": true,
    "samesite": "Lax"
  }
}
```

### 2. OAuth Callback Success Logging (`oauth.callback.success`)

**Location**: `app/api/google_oauth.py` - `google_callback()` function

**Log Level**: INFO

**Message**: `"oauth.callback.success"`

**Required Fields**:
- `state_valid`: boolean - Whether the OAuth state validation passed
- `token_exchange`: string - Status of token exchange (`"ok"` for success)
- `set_auth_cookies`: boolean - Whether authentication cookies were set
- `redirect`: string - The final redirect URL

**Example Log**:
```json
{
  "timestamp": "2025-08-21T14:46:02Z",
  "req_id": "9b3e1a10-d45f-40b6-afc7-e4525bfe38db",
  "level": "INFO",
  "component": "app.api.google_oauth",
  "msg": "oauth.callback.success",
  "meta": {
    "req_id": "9b3e1a10-d45f-40b6-afc7-e4525bfe38db",
    "component": "google_oauth",
    "msg": "oauth.callback.success",
    "state_valid": true,
    "token_exchange": "ok",
    "set_auth_cookies": true,
    "redirect": "http://localhost:3000/"
  }
}
```

### 3. OAuth Callback Failure Logging (`oauth.callback.fail`)

**Location**: `app/api/google_oauth.py` - `google_callback()` function

**Log Level**: WARN/ERROR

**Message**: `"oauth.callback.fail"`

**Required Fields**:
- `state_valid`: boolean - Whether the OAuth state validation passed
- `token_exchange`: string - Status of token exchange (`"fail"` for failure)
- `google_status`: integer - HTTP status code from Google
- `reason`: string - Reason for failure (always `"oauth_exchange_failed"`)
- `redirect`: string - Error redirect URL

**Example Log**:
```json
{
  "timestamp": "2025-08-21T14:46:03Z",
  "req_id": "9b3e1a10-d45f-40b6-afc7-e4525bfe38db",
  "level": "ERROR",
  "component": "app.api.google_oauth",
  "msg": "oauth.callback.fail",
  "meta": {
    "req_id": "9b3e1a10-d45f-40b6-afc7-e4525bfe38db",
    "component": "google_oauth",
    "msg": "oauth.callback.fail",
    "state_valid": true,
    "token_exchange": "fail",
    "google_status": 400,
    "reason": "oauth_exchange_failed",
    "redirect": "/login?err=oauth_exchange_failed"
  }
}
```

### 4. HTTP Out Logging for Google Token Exchange

**Location**: `app/api/google_oauth.py` - `google_callback()` function

**Log Level**: INFO

**Message**: External service call logging

**Structure**: Child log with `http_out` metadata

**Example Log**:
```json
{
  "timestamp": "2025-08-21T14:46:02Z",
  "req_id": "9b3e1a10-d45f-40b6-afc7-e4525bfe38db",
  "level": "INFO",
  "component": "app.api.google_oauth",
  "msg": "External call: google_token -> 200 (123.4ms)",
  "meta": {
    "req_id": "9b3e1a10-d45f-40b6-afc7-e4525bfe38db",
    "http_out": {
      "service": "google_token",
      "status": 200,
      "latency_ms": 123.4
    },
    "exchange_status": "ok"
  }
}
```

### 5. Google Response Body Debug Logging

**Location**: `app/api/google_oauth.py` - `google_callback()` function

**Log Level**: DEBUG

**Message**: `"Google response body (first 200 chars)"`

**Purpose**: Logs first 200 characters of Google's response body on failures (never dumps full JSON with tokens)

**Example Log**:
```json
{
  "timestamp": "2025-08-21T14:46:03Z",
  "req_id": "9b3e1a10-d45f-40b6-afc7-e4525bfe38db",
  "level": "DEBUG",
  "component": "app.api.google_oauth",
  "msg": "Google response body (first 200 chars)",
  "meta": {
    "req_id": "9b3e1a10-d45f-40b6-afc7-e4525bfe38db",
    "component": "google_oauth",
    "msg": "google_response_body",
    "response_body": "{\"error\":\"invalid_grant\",\"error_description\":\"The authorization code has expired or is invalid\"}"
  }
}
```

### 6. Whoami Authentication Logging (`auth.whoami`)

**Location**: `app/api/auth.py` - `whoami()` and `auth_whoami()` functions

**Log Level**: INFO

**Message**: `"auth.whoami"`

**Required Fields**:
- `status`: integer - HTTP status code (200 for success, 401 for failure)
- `user_id`: string - User ID if present, `null` for anonymous users
- `duration_ms`: float - Request duration in milliseconds

**Example Log**:
```json
{
  "timestamp": "2025-08-21T14:46:04Z",
  "req_id": "9b3e1a10-d45f-40b6-afc7-e4525bfe38db",
  "level": "INFO",
  "component": "app.api.auth",
  "msg": "auth.whoami",
  "meta": {
    "req_id": "9b3e1a10-d45f-40b6-afc7-e4525bfe38db",
    "component": "auth",
    "msg": "auth.whoami",
    "status": 200,
    "user_id": "test_user",
    "duration_ms": 15.2
  }
}
```

## Implementation Details

### Files Modified

1. **`app/api/google_oauth.py`**
   - Added structured logging for OAuth login URL generation
   - Added structured logging for OAuth callback success/failure
   - Added HTTP out logging for Google token exchange
   - Added DEBUG logging for Google response body on failures
   - Added timing measurements for all operations

2. **`app/api/auth.py`**
   - Added structured logging for whoami endpoints
   - Added timing measurements for whoami requests
   - Added import for `req_id_var` from logging configuration

3. **`tests/unit/test_oauth_logging.py`**
   - Created unit tests to verify structured logging functionality
   - Tests cover all required logging patterns and field validation

4. **`tests/integration/test_oauth_logging_integration.py`**
   - Created integration tests to verify logging in real environment
   - Tests use actual HTTP requests and capture real log output

### Key Features

1. **Consistent Structure**: All logs follow the same structured format with `meta` field containing relevant data
2. **Request Tracing**: All logs include `req_id` for request correlation
3. **Timing Information**: Duration measurements for performance monitoring
4. **Security**: No sensitive data (tokens) logged in production
5. **Debug Support**: Limited response body logging for troubleshooting
6. **Error Handling**: Comprehensive error logging with structured metadata

### Logging Configuration

The implementation leverages the existing logging configuration in `app/logging_config.py`:
- Uses JSON formatter for structured output
- Includes request ID correlation
- Supports both development and production modes
- Integrates with existing log filters and handlers

## Testing

### Unit Tests
- `test_oauth_login_url_logging()` - Verifies login URL logging structure
- `test_oauth_callback_success_logging()` - Verifies successful callback logging
- `test_oauth_callback_failure_logging()` - Verifies failure callback logging
- `test_whoami_logging()` - Verifies whoami endpoint logging
- `test_http_out_logging()` - Verifies external call logging

### Integration Tests
- `test_oauth_login_url_logging_integration()` - End-to-end login URL test
- `test_whoami_logging_integration()` - End-to-end whoami test
- `test_oauth_callback_failure_logging_integration()` - End-to-end failure test

## Usage

The structured logging is automatically enabled when OAuth flows are used. No additional configuration is required. Logs will appear in the configured output (stdout/stderr) with the structured format described above.

## Monitoring

These logs can be used for:
- **Authentication Flow Monitoring**: Track OAuth success/failure rates
- **Performance Monitoring**: Monitor token exchange latency
- **Security Monitoring**: Track authentication attempts and failures
- **Debugging**: Use DEBUG logs to troubleshoot OAuth issues
- **Analytics**: Analyze user authentication patterns

## Security Considerations

1. **No Token Logging**: Access tokens and refresh tokens are never logged
2. **Limited Response Body**: Only first 200 characters of error responses are logged
3. **Structured Data**: All sensitive data is properly sanitized before logging
4. **Request Correlation**: Request IDs allow tracing without exposing user data
