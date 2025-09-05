# Domain: CSRF / CORS / Middleware

## Current Purpose

The CSRF/CORS/Middleware domain handles cross-site request protection, cross-origin resource sharing, and request processing pipeline management for the GesahniV2 application. It provides:

- **CSRF Protection** with double-submit cookie pattern and configurable exemptions for OAuth callbacks and webhooks
- **CORS Management** with origin validation, preflight handling, and credentials support
- **Middleware Pipeline** with 15+ middleware components for observability, security, and request processing
- **Request Lifecycle Management** from entry through response with tracing, metrics, and error handling
- **Rate Limiting** with per-IP and per-user throttling to prevent abuse
- **Session Management** with automatic refresh, attach, and cleanup
- **Security Headers** including HSTS, CSP, referrer policy, and content-type options
- **Idempotency Support** with request deduplication and cached responses
- **Audit Logging** with comprehensive request/response tracking and telemetry
- **Error Handling** with structured error responses and fallback mechanisms

## Entry Points (Routes, Hooks, Startup Tasks)

### HTTP Request Lifecycle

- **All HTTP Requests** → `app.middleware.stack.setup_middleware_stack()` - Main middleware pipeline setup
- **CORS Preflight** → `app.middleware.cors.CorsPreflightMiddleware` - OPTIONS request handling
- **CSRF Validation** → `app.csrf.CSRFMiddleware` - State-changing request protection
- **Rate Limiting** → `app.middleware.rate_limit.RateLimitMiddleware` - Request throttling
- **Session Attach** → `app.middleware.session_attach.SessionAttachMiddleware` - User session binding

### Startup Tasks

- **Middleware Registration** → `app.middleware.stack.setup_middleware_stack()` - Complete pipeline assembly
- **CORS Configuration** → `app.settings_cors.get_cors_origins()` - Origin validation and setup
- **CSRF Token Store** → `app.csrf._csrf_token_store` - Server-side token storage initialization
- **Rate Limit Initialization** → `app.middleware.rate_limit.RateLimitMiddleware` - Limit configuration
- **Audit Setup** → `app.middleware.audit_mw.AuditMiddleware` - Logging configuration

### WebSocket Integration

- **WebSocket Handshakes** → CORS validation for WebSocket connections
- **WS Rate Limiting** → Per-user WebSocket connection throttling
- **Origin Validation** → Same CORS origin checks for WebSocket upgrades

## Internal Dependencies

### Core Middleware Components
- **`app.csrf.CSRFMiddleware`** - CSRF token validation and header management
- **`app.middleware.cors.CorsMiddleware`** - Origin validation and CORS header injection
- **`app.middleware.cors.CorsPreflightMiddleware`** - OPTIONS preflight request handling
- **`app.middleware.rate_limit.RateLimitMiddleware`** - Request throttling and burst control
- **`app.middleware.session_attach.SessionAttachMiddleware`** - User session binding and JWT parsing

### Request Processing Pipeline
- **`app.middleware.middleware_core.RequestIDMiddleware`** - Unique request ID generation and propagation
- **`app.middleware.middleware_core.TraceRequestMiddleware`** - OpenTelemetry tracing and logging
- **`app.middleware.middleware_core.DedupMiddleware`** - Request deduplication and idempotency
- **`app.middleware.middleware_core.HealthCheckFilterMiddleware`** - Health endpoint filtering
- **`app.middleware.middleware_core.RedactHashMiddleware`** - Sensitive header redaction

### Observability and Security
- **`app.middleware.audit_mw.AuditMiddleware`** - Comprehensive request/response auditing
- **`app.middleware.metrics_mw.MetricsMiddleware`** - Prometheus metrics collection
- **`app.middleware.error_handler.ErrorHandlerMiddleware`** - Error response formatting
- **`app.middleware.custom.SilentRefreshMiddleware`** - JWT token automatic refresh
- **`app.middleware.custom.ReloadEnvMiddleware`** - Development environment reloading

### Configuration and Settings
- **`app.settings_cors`** - CORS origin parsing and validation logic
- **`app.cookie_config`** - Cookie security settings and SameSite configuration
- **`app.cookies`** - Cookie helper functions and centralized cookie management
- **`app.tokens`** - JWT token creation and validation utilities

## External Dependencies

### Web Standards and Security
- **HTTP Headers** - Standard security headers (HSTS, CSP, Referrer-Policy, X-Frame-Options)
- **Cookie Attributes** - Secure, HttpOnly, SameSite cookie configuration
- **CORS Protocol** - W3C CORS specification compliance
- **CSRF Protection** - Double-submit cookie pattern with server-side validation

### Storage Systems
- **Redis** - Optional server-side CSRF token storage (falls back to in-memory)
- **In-memory Cache** - TTLCache for request deduplication and idempotency
- **File System** - Audit log persistence and configuration loading

### Third-party Libraries
- **Starlette CORSMiddleware** - Standard CORS implementation
- **Cachetools TTLCache** - Time-based cache with automatic expiration
- **JWT Library** - JSON Web Token encoding/decoding
- **OpenTelemetry** - Distributed tracing and observability

### Environment Configuration
- **Environment Variables** - CSRF_ENABLED, CORS_ALLOW_ORIGINS, COOKIE_SAMESITE
- **Runtime Configuration** - Dynamic middleware enabling/disabling
- **Development Mode** - Hot reloading and debug features

## Invariants / Assumptions

- **Middleware Order Matters**: CORS must be outermost, CSRF before auth, rate limiting before session attach
- **OPTIONS Bypass**: All middlewares must skip processing for OPTIONS preflight requests
- **Cookie Dependencies**: CSRF validation assumes presence of session/auth cookies
- **Origin Validation**: CORS assumes localhost variants are always allowed in development
- **Request ID Propagation**: All middlewares assume X-Request-ID header will be set by RequestIDMiddleware
- **JWT Secret Required**: Token refresh middleware assumes JWT_SECRET environment variable exists
- **Rate Limit Exemptions**: Health checks and static assets bypass rate limiting
- **Audit Logging**: All middlewares assume audit logging will not fail requests
- **Error Handling**: Middlewares never raise exceptions - they return error responses instead
- **Environment Consistency**: Production settings assume HTTPS and secure cookie attributes

## Known Weirdness / Bugs

- **Middleware Order Validation**: No runtime enforcement of correct middleware ordering
- **CORS Origin Mixing**: Mixed localhost/IP origins can cause WebSocket connection issues
- **CSRF Token Race**: Multiple concurrent requests can create duplicate CSRF tokens
- **Rate Limit Headers**: Rate limit headers added even for exempted requests
- **Silent Refresh Timing**: Token refresh can cause timing issues with concurrent requests
- **Audit Log Failures**: Audit middleware failures are silently ignored, losing observability
- **Error Handler Conflicts**: Multiple error handlers can conflict in response formatting
- **WebSocket CORS**: WebSocket connections don't properly inherit CORS settings
- **Cache Memory Leaks**: In-memory caches can grow indefinitely without cleanup mechanisms
- **Header Redaction**: Sensitive header redaction happens after logging, creating timing windows

## Observed Behavior

### Request Flow Priority

1. **CORS Preflight** → OPTIONS requests handled immediately with CORS headers
2. **Request ID Assignment** → Unique ID generated and propagated to all logs/metrics
3. **Origin Validation** → CORS origin checked against allowed list
4. **Rate Limiting** → Request count checked against per-IP/per-user limits
5. **Session Attachment** → JWT tokens decoded and user context established
6. **CSRF Validation** → Token validation for state-changing requests
7. **Deduplication** → Request ID checked for duplicate prevention
8. **Tracing Start** → OpenTelemetry span created for observability
9. **Audit Logging** → Request details logged for compliance
10. **Application Logic** → Request reaches actual route handlers
11. **Response Processing** → Headers added, metrics collected
12. **Error Handling** → Structured error responses with appropriate status codes

### Response Headers Added

**Security Headers:**
```
Strict-Transport-Security: max-age=63072000; includeSubDomains; preload
Referrer-Policy: no-referrer
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Permissions-Policy: camera=(), microphone=(), geolocation=()
```

**CORS Headers:**
```
Access-Control-Allow-Origin: https://allowed-domain.com
Access-Control-Allow-Credentials: true
Access-Control-Expose-Headers: X-Request-ID,X-Trace-ID
```

**Rate Limit Headers:**
```
RateLimit-Limit: 100
RateLimit-Remaining: 95
RateLimit-Reset: 1640995200
X-RateLimit-Burst-Limit: 20
X-RateLimit-Burst-Remaining: 18
```

### Status Code Responses

- **200 OK**: Successful request processing
- **400 Bad Request**: Invalid CORS origin, malformed CSRF token, invalid request format
- **401 Unauthorized**: Missing authentication, invalid JWT token
- **403 Forbidden**: CSRF validation failure, insufficient scope, rate limit exceeded
- **404 Not Found**: Invalid route (passes through middleware unchanged)
- **405 Method Not Allowed**: HTTP method not in CORS allowed methods
- **409 Conflict**: Duplicate request ID (deduplication)
- **415 Unsupported Media Type**: Content-Type not supported
- **429 Too Many Requests**: Rate limit exceeded
- **500 Internal Server Error**: Middleware processing failures
- **503 Service Unavailable**: Backend unavailable, circuit breaker open

### CSRF Token Flow

1. **GET Request**: CSRF token cookie set automatically, X-CSRF-Token header mirrored
2. **POST/PUT/PATCH/DELETE**: Token validated against cookie, mismatch returns 403
3. **Bearer Auth Bypass**: Authorization header presence skips CSRF validation
4. **OAuth Callback Bypass**: Specific callback paths skip CSRF validation
5. **Webhook Bypass**: Signature validation replaces CSRF for webhook endpoints

### CORS Validation Flow

1. **Origin Check**: Request Origin header validated against allowed origins
2. **Preflight Handling**: OPTIONS requests validated and responded with CORS headers
3. **Credentials Support**: Access-Control-Allow-Credentials set for authenticated requests
4. **Header Validation**: Access-Control-Request-Headers validated for preflights
5. **Error Responses**: Invalid origins still get CORS headers to prevent information leakage

## TODOs / Redesign Ideas

### Immediate Issues
- **Middleware Order Enforcement**: Add runtime validation of correct middleware stack ordering
- **WebSocket CORS Inheritance**: Ensure WebSocket connections properly inherit CORS settings
- **Cache Cleanup Mechanisms**: Implement TTL-based cleanup for in-memory caches
- **Audit Failure Handling**: Add structured handling for audit middleware failures
- **Header Redaction Timing**: Fix timing window where sensitive headers are logged before redaction

### Architecture Improvements
- **Middleware Dependency Injection**: Move from global middleware registration to DI pattern
- **Configuration Validation**: Add startup-time validation of CORS origins and security settings
- **Error Handler Consolidation**: Merge multiple error handlers into single unified system
- **Rate Limit Algorithm**: Implement more sophisticated rate limiting (sliding window vs fixed window)
- **CSRF Token Store Interface**: Abstract CSRF storage behind interface for different backends

### Security Enhancements
- **CSRF Token Rotation**: Implement automatic token rotation on successful requests
- **Origin Validation Strictness**: Add more sophisticated origin validation for production
- **Rate Limit Granularity**: Add per-endpoint rate limiting with different limits
- **Session Fingerprinting**: Add device fingerprinting for enhanced session security
- **Audit Log Encryption**: Encrypt sensitive data in audit logs for compliance

### Observability Improvements
- **Middleware Performance Metrics**: Add detailed timing metrics for each middleware
- **Error Correlation**: Better correlation between middleware errors and application errors
- **Configuration Drift Detection**: Detect when middleware configuration drifts from expected
- **Security Event Alerting**: Real-time alerting for security events (CSRF failures, rate limit hits)
- **Request Tracing Enhancement**: Add middleware-specific spans to distributed traces

### Future Capabilities
- **Adaptive Rate Limiting**: ML-based rate limiting that adapts to user behavior patterns
- **Dynamic CORS**: Runtime CORS origin management for multi-tenant applications
- **CSRF Token Management API**: REST API for CSRF token lifecycle management
- **Middleware Hot Swapping**: Ability to enable/disable middlewares without restart
- **Security Policy Engine**: Pluggable security policy system for custom validation rules
