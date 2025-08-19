# JWT Secret Fallback Security Fix

## Issue Summary

**Location**: `app/api/auth.py` lines 380-390 and related files

**Problem**: The JWT secret fallback mechanism used hardcoded default values like "change-me" which created several security vulnerabilities:

1. **Insecure in production**: Hardcoded secrets are predictable and vulnerable to attacks
2. **Accidental deployment risk**: Default values could be accidentally left in production environments
3. **Predictable tokens**: JWT tokens signed with known secrets are easily forgeable
4. **Health check bypass**: The health check only verified presence, not security of the secret

## Root Cause Analysis

The issue was present in multiple locations:

### 1. Primary JWT Secret Functions (`app/api/auth.py`)
```python
# BEFORE (Insecure)
def _jwt_secret() -> str:
    sec = os.getenv("JWT_SECRET")
    if not sec:
        return os.getenv("JWT_SECRET", "change-me")  # Insecure fallback
    return sec

def _key_pool_from_env() -> dict[str, str]:
    # ... parsing logic ...
    sec = os.getenv("JWT_SECRET")
    if not sec:
        sec = "change-me"  # Insecure fallback
    return {"k0": sec}
```

### 2. Legacy Auth Module (`app/auth.py`)
```python
# BEFORE (Insecure)
SECRET_KEY = os.getenv("JWT_SECRET", "change-me")  # Insecure fallback
```

### 3. Caregiver Auth (`app/api/caregiver_auth.py`)
```python
# BEFORE (Insecure)
def _secret() -> str:
    return os.getenv("CARE_ACK_SECRET", os.getenv("JWT_SECRET", "change-me"))
```

### 4. Health Check (`app/health_utils.py`)
```python
# BEFORE (Insufficient)
async def check_jwt_secret() -> HealthResult:
    return "ok" if (os.getenv("JWT_SECRET") or os.getenv("JWT_PUBLIC_KEY")) else "error"
```

## Security Fix Implementation

### 1. Remove Insecure Fallbacks

**Files Modified**:
- `app/api/auth.py`
- `app/auth.py` 
- `app/api/caregiver_auth.py`

**Changes**:
- Removed all hardcoded "change-me" fallbacks
- Added proper error handling with `HTTPException(status_code=500, detail="missing_jwt_secret")`
- Added security validation to detect insecure default values

### 2. Enhanced Security Validation

**New Security Checks**:
```python
# Security check: prevent use of default/placeholder secrets
if sec.strip().lower() in {"change-me", "default", "placeholder", "secret", "key"}:
    raise HTTPException(status_code=500, detail="insecure_jwt_secret")
```

**Detected Insecure Values**:
- `change-me` (original fallback)
- `default`
- `placeholder` 
- `secret`
- `key`

### 3. Improved Health Check

**Enhanced Health Check** (`app/health_utils.py`):
```python
async def check_jwt_secret() -> HealthResult:
    jwt_secret = os.getenv("JWT_SECRET")
    jwt_public_key = os.getenv("JWT_PUBLIC_KEY")
    
    # Check if JWT_SECRET is configured
    if not jwt_secret and not jwt_public_key:
        return "error"
    
    # Security check: detect insecure default values
    if jwt_secret and jwt_secret.strip().lower() in {"change-me", "default", "placeholder", "secret", "key"}:
        return "error"
    
    return "ok"
```

### 4. Updated Test Suite

**New Test File**: `tests/unit/test_jwt_secret_security.py`

**Test Coverage**:
- Missing JWT secret detection
- Insecure default value detection (case-insensitive)
- Empty/whitespace secret detection
- Secure secret validation
- Caregiver auth security
- Health check security validation

**Updated Existing Tests**:
- `tests/unit/test_auth_token_endpoint_unit.py`
- `tests/unit/test_auth_contract_locked.py`

## Security Impact

### Before Fix
- ❌ JWT tokens could be forged with known "change-me" secret
- ❌ Default secrets could be deployed to production
- ❌ Health checks would pass with insecure secrets
- ❌ No validation of secret quality

### After Fix
- ✅ No hardcoded secrets in codebase
- ✅ Clear error messages for missing/insecure secrets
- ✅ Health checks detect insecure configurations
- ✅ Case-insensitive detection of common insecure values
- ✅ Proper error handling prevents silent failures

## Error Messages

**Missing Secret**:
```json
{
  "detail": "missing_jwt_secret"
}
```

**Insecure Secret**:
```json
{
  "detail": "insecure_jwt_secret"
}
```

**Caregiver Auth Missing Secret**:
```json
{
  "detail": "missing_care_secret"
}
```

**Caregiver Auth Insecure Secret**:
```json
{
  "detail": "insecure_care_secret"
}
```

## Health Check Behavior

**Missing/Insecure JWT Secret**:
```json
{
  "status": "fail",
  "failing": ["jwt"]
}
```

**Secure JWT Secret**:
```json
{
  "status": "ok"
}
```

## Migration Guide

### For Development
1. Set a secure `JWT_SECRET` environment variable
2. Ensure the secret is not in the insecure values list
3. Use strong, randomly generated secrets

### For Production
1. **Immediate Action Required**: Set `JWT_SECRET` to a secure value
2. **Recommended**: Use a secrets management system
3. **Validation**: Verify health check passes (`/healthz/ready`)
4. **Monitoring**: Set up alerts for health check failures

### Example Secure Secret Generation
```bash
# Generate a secure 32-byte secret
openssl rand -base64 32

# Or use Python
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

## Testing

Run the security test suite:
```bash
python -m pytest tests/unit/test_jwt_secret_security.py -v
```

Run all affected tests:
```bash
python -m pytest tests/unit/test_auth_token_endpoint_unit.py tests/unit/test_auth_contract_locked.py tests/unit/test_jwt_secret_security.py -v
```

## Compliance

This fix addresses several security best practices:
- **OWASP Top 10**: A02:2021 - Cryptographic Failures
- **Security Principle**: Fail securely, not silently
- **Defense in Depth**: Multiple layers of validation
- **Security by Design**: Proactive detection of insecure configurations

## Files Modified

1. `app/api/auth.py` - Primary JWT secret functions
2. `app/auth.py` - Legacy auth module
3. `app/api/caregiver_auth.py` - Caregiver authentication
4. `app/health_utils.py` - Health check validation
5. `tests/unit/test_auth_token_endpoint_unit.py` - Updated tests
6. `tests/unit/test_auth_contract_locked.py` - Updated tests
7. `tests/unit/test_jwt_secret_security.py` - New security tests

## Risk Assessment

**Risk Level**: HIGH → LOW

**Before**: Critical security vulnerability allowing JWT forgery
**After**: Secure by default with clear error handling

**Mitigation**: 
- Immediate deployment recommended
- No breaking changes for properly configured systems
- Clear error messages guide proper configuration
