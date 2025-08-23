# Environment Configuration Matrix

This document outlines the key environment variables that control authentication and security behavior in the application.

## Core Authentication Variables

### `JWT_SECRET` (Required)
**Purpose**: JWT signing secret for access and refresh tokens
**Default**: None (must be set)
**Security Level**: CRITICAL
**Validation**:
- Must be set (cannot be empty)
- Must not contain common insecure values: `change-me`, `default`, `placeholder`, `secret`, `key`
- Must be >= 32 characters (recommended >= 64)
- Can be relaxed with `DEV_MODE=1` (with warning)

### `CLERK_ENABLED` (Optional)
**Purpose**: Enable Clerk authentication integration
**Default**: `"0"` (disabled)
**Security Level**: MEDIUM
**Behavior**:
- `"0"`: Clerk cookies/headers ignored completely
- `"1"`: Enables Clerk token verification for `__session` cookies and Authorization headers
**Note**: When disabled, no Clerk code paths are executed for security

### `DEV_MODE` (Optional)
**Purpose**: Enable development mode with relaxed security
**Default**: `"0"` (production mode)
**Security Level**: HIGH (use only in development)
**Behavior**:
- `"0"`: Strict JWT secret validation and security checks
- `"1"`: Allows weak JWT secrets with warning, enables debug features
**Warning**: Never set to `"1"` in production environments

## Security Variables

### `CSRF_ENABLED` (Optional)
**Purpose**: Enable CSRF protection on state-changing endpoints
**Default**: `"1"` (enabled)
**Security Level**: HIGH
**Behavior**:
- `"0"`: Disable CSRF token validation (development only)
- `"1"`: Require valid CSRF tokens for POST/PUT/DELETE requests
**Note**: Should be enabled in production, can be disabled for API-only usage

### `COOKIE_SAMESITE` (Optional)
**Purpose**: Control SameSite attribute for authentication cookies
**Default**: `"Lax"`
**Security Level**: MEDIUM
**Valid Values**: `"Lax"`, `"Strict"`, `"None"`
**Behavior**:
- `"Lax"`: Cookies sent with top-level navigation (balanced security/usability)
- `"Strict"`: Cookies only sent to same-site requests (maximum security)
- `"None"`: Cookies sent with cross-site requests (requires Secure flag)
**Note**: `"None"` requires HTTPS and Secure flag to be set

## Cookie Configuration Variables

### `COOKIE_SECURE` (Optional)
**Purpose**: Control Secure flag for authentication cookies
**Default**: Auto-detected based on request scheme
**Security Level**: MEDIUM
**Valid Values**: `"1"`, `"0"`, `"auto"`
**Behavior**:
- `"1"`: Always set Secure flag (HTTPS only)
- `"0"`: Never set Secure flag (allows HTTP)
- `"auto"`: Set Secure flag only for HTTPS requests
**Note**: Should be `"1"` or `"auto"` in production

### `COOKIE_DOMAIN` (Optional)
**Purpose**: Set domain attribute for authentication cookies
**Default**: None (current domain only)
**Security Level**: LOW
**Behavior**: Controls which domains can access the cookies
**Use Case**: Multi-subdomain setups requiring shared authentication

### `COOKIE_SAMESITE` (See above - controls SameSite attribute)

## Development and Testing Variables

### `JWT_CLOCK_SKEW_S` (Optional)
**Purpose**: Clock skew tolerance for JWT validation
**Default**: `"60"` (60 seconds)
**Security Level**: LOW
**Behavior**: Allows time difference tolerance between token issuer and validator
**Use Case**: Handling minor clock differences in distributed systems

### `DEBUG_MODEL_ROUTING` (Optional)
**Purpose**: Log model routing decisions without making external calls
**Default**: `"0"` (disabled)
**Security Level**: LOW
**Behavior**: Enables debug logging for model routing logic
**Use Case**: Development and troubleshooting

### `LOG_LEVEL` (Optional)
**Purpose**: Set application logging verbosity
**Default**: `"INFO"`
**Security Level**: LOW
**Valid Values**: `"DEBUG"`, `"INFO"`, `"WARNING"`, `"ERROR"`, `"CRITICAL"`
**Note**: `"DEBUG"` may expose sensitive information in logs

## Production Recommendations

### Minimum Production Configuration
```bash
# Required
JWT_SECRET="your-super-secure-jwt-secret-key-here"

# Recommended Security Settings
CLERK_ENABLED="0"          # Disable if not using Clerk
DEV_MODE="0"              # Never enable in production
CSRF_ENABLED="1"          # Enable CSRF protection
COOKIE_SAMESITE="Lax"     # Balanced security/usability
COOKIE_SECURE="auto"      # HTTPS detection
```

### Development Configuration
```bash
# Development settings with warnings
JWT_SECRET="dev-secret-key-for-testing-only"
DEV_MODE="1"              # Enables warnings for weak settings
CSRF_ENABLED="0"          # Disable for easier testing
LOG_LEVEL="DEBUG"         # Enable debug logging
```

### Testing Configuration
```bash
# Test environment
JWT_SECRET="test-secret-key"
DEV_MODE="0"              # Tests should exercise strict validation
LOG_LEVEL="WARNING"       # Reduce noise during testing
```

## Environment Variable Interactions

### JWT Security Bypass
- `DEV_MODE=1` allows weak `JWT_SECRET` with warning
- `CLERK_ENABLED=1` enables Clerk authentication paths
- Both can be set independently

### Cookie Security Matrix
```
COOKIE_SAMESITE + HTTPS + COOKIE_SECURE = Security Level

Lax + HTTPS + auto    = Balanced (recommended)
Strict + HTTPS + auto = Maximum security
None + HTTPS + 1      = Cross-site allowed (requires HTTPS)
```

### CSRF and Development
- `CSRF_ENABLED=0` bypasses CSRF validation
- Useful for API testing and development
- Should be combined with `DEV_MODE=1` for consistency

## Security Considerations

### Critical Variables (Set in Production)
- `JWT_SECRET`: Must be cryptographically secure
- `CLERK_ENABLED`: Should be `"0"` unless actively using Clerk
- `DEV_MODE`: Must be `"0"` in production

### Medium Risk Variables (Review for Production)
- `COOKIE_SAMESITE`: `"Lax"` is generally safe
- `COOKIE_SECURE`: Should be `"auto"` or `"1"`
- `CSRF_ENABLED`: Should be `"1"` for web applications

### Low Risk Variables (Development Focused)
- `LOG_LEVEL`: Debug level may expose information
- `JWT_CLOCK_SKEW_S`: Affects token validation windows
- `DEBUG_MODEL_ROUTING`: Only affects logging

## Migration Notes

### From Previous Versions
- `JWT_SECRET` validation is now stricter
- `DEV_MODE=1` provides migration path for weak secrets
- `CLERK_ENABLED` now completely disables Clerk paths when `"0"`

### Breaking Changes
- Weak `JWT_SECRET` values now rejected by default
- Clerk cookies ignored when `CLERK_ENABLED=0` (stricter)
- CSRF protection enabled by default

## Monitoring and Alerts

Consider monitoring these environment variables in production:

1. **Alert on**: `DEV_MODE=1` (should never be set in production)
2. **Alert on**: `JWT_SECRET` changes (may indicate compromise)
3. **Alert on**: `CLERK_ENABLED` changes (affects authentication flow)
4. **Monitor**: Weak JWT secret warnings in logs (DEV_MODE=1 usage)
