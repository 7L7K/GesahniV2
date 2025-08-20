# Token Minting Centralization Summary

## Current State: ✅ COMPLETE

The token minting surface has been successfully centralized according to the requirements. All application access/refresh JWT tokens are now minted exclusively through `app/tokens.py`.

## Centralized Token Creation

### Primary Functions in `app/tokens.py`:
- `make_access(claims, *, ttl_s=None, alg=None, key=None, kid=None)` - Creates access tokens
- `make_refresh(claims, *, ttl_s=None, alg=None, key=None, kid=None)` - Creates refresh tokens
- `get_default_access_ttl()` - Gets default access token TTL
- `get_default_refresh_ttl()` - Gets default refresh token TTL

### Deprecated Functions (with warnings):
- `create_access_token()` - **DEPRECATED** - Use `make_access()` instead
- `create_refresh_token()` - **DEPRECATED** - Use `make_refresh()` instead

## JWT.encode Usage Analysis

### ✅ Allowed JWT.encode Calls:

1. **`app/tokens.py`** (Lines 77, 121)
   - **Purpose**: Centralized application token creation
   - **Algorithm**: HS256
   - **Status**: ✅ CORRECT - This is the only place application tokens should be minted

2. **`app/api/oauth_apple.py`** (Line 44)
   - **Purpose**: Apple OAuth integration
   - **Algorithm**: ES256 (Apple-specific requirement)
   - **Status**: ✅ ALLOWED EXCEPTION - IdP-specific signer as specified in requirements

### ✅ Test Files (Expected):
All other `jwt.encode` calls are in test files (`tests/` directory), which is expected and acceptable for testing purposes.

## Implementation Details

### Token Normalization
The centralized functions provide:
- Automatic claim normalization (`sub` ↔ `user_id` mapping)
- Standard scope defaults (`["care:resident", "music:control"]`)
- Automatic JTI generation for refresh tokens
- Centralized TTL management

### Environment Configuration
- `JWT_SECRET` - Required for token signing
- `JWT_ACCESS_TTL_SECONDS` / `JWT_EXPIRE_MINUTES` - Access token TTL
- `JWT_REFRESH_TTL_SECONDS` / `JWT_REFRESH_EXPIRE_MINUTES` - Refresh token TTL
- `JWT_ISS` - Optional issuer claim
- `JWT_AUD` - Optional audience claim

### Security Features
- JWT secret validation (prevents insecure defaults)
- Automatic expiration handling
- Unique JTI (JWT ID) for each token
- Proper claim structure and validation

## Usage Examples

### Creating Access Tokens:
```python
from app.tokens import make_access

# Basic usage
token = make_access({"sub": "user123"})

# With custom TTL
token = make_access({"sub": "user123"}, ttl_s=3600)  # 1 hour

# With custom scopes
token = make_access({"sub": "user123", "scopes": ["admin:write"]})
```

### Creating Refresh Tokens:
```python
from app.tokens import make_refresh

# Basic usage
token = make_refresh({"sub": "user123"})

# With custom TTL
token = make_refresh({"sub": "user123"}, ttl_s=86400)  # 24 hours
```

## Migration Status

### ✅ Completed:
- All application code uses centralized token functions
- Legacy functions marked as deprecated with warnings
- Apple OAuth integration properly isolated as allowed exception
- Test files remain unchanged (as expected)

### ✅ Verification:
- Token creation works correctly
- Proper claim structure and expiration
- Deprecation warnings appear for legacy function usage
- No unauthorized JWT.encode calls in application code

## Compliance with Requirements

1. ✅ **Single Minting Point**: `app/tokens.py` is the only place that mints application access/refresh JWTs
2. ✅ **Public Helpers**: `make_access()` and `make_refresh()` provide clean public interfaces
3. ✅ **IdP Exceptions**: Apple OAuth integration uses ES256 as allowed exception
4. ✅ **No Local JWT.encode**: No unauthorized JWT.encode calls for app tokens outside tokens.py
5. ✅ **Legacy Handling**: Deprecated functions provide migration path with warnings

## Conclusion

The token minting surface has been successfully locked down and centralized. All application JWT tokens are now created through the single, well-defined interface in `app/tokens.py`, providing:

- **Security**: Centralized secret management and validation
- **Consistency**: Standardized claim structure and TTL handling
- **Maintainability**: Single point of control for token creation logic
- **Flexibility**: Support for custom TTLs and claims while maintaining defaults

The implementation fully satisfies the requirements while maintaining backward compatibility through deprecated wrapper functions.
