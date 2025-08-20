# Token Minting Surface Lockdown Summary

## Overview
Successfully locked down the token minting surface by deprecating old token creation functions and ensuring OAuth IdP-specific token signing remains properly isolated.

## Changes Made

### 1. Deprecated Old Token Creation Functions in `app/auth.py`
- **File**: `app/auth.py`
- **Change**: Commented out the import of old `create_access_token` and `create_refresh_token` functions
- **Reason**: These functions are no longer used in auth.py and are deprecated in favor of the centralized functions in tokens.py

```python
# Note: These functions are deprecated in favor of make_access() and make_refresh()
# from .tokens import create_access_token, create_refresh_token
```

### 2. Added Deprecation Warnings in `app/tokens.py`
- **File**: `app/tokens.py`
- **Change**: Added proper deprecation warnings to `create_access_token` and `create_refresh_token` functions
- **Reason**: Maintain backward compatibility while encouraging migration to new functions

```python
# DEPRECATED: Use make_access() and make_refresh() instead for better TTL management and claim normalization
import warnings

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token with the given data.
    
    DEPRECATED: Use make_access() instead for better TTL management and claim normalization.
    """
    warnings.warn(
        "create_access_token is deprecated. Use make_access() instead for better TTL management and claim normalization.",
        DeprecationWarning,
        stacklevel=2
    )
    return _create_access_token_internal(data, expires_delta=expires_delta)
```

### 3. Verified OAuth IdP Token Signing Isolation
- **File**: `app/api/oauth_apple.py`
- **Status**: ✅ Properly isolated
- **Function**: `_sign_client_secret()` uses ES256 algorithm for Apple OAuth
- **Reason**: This is IdP-specific token signing, not app session token creation, so it correctly remains outside tokens.py

## Current Token Minting Surface

### ✅ Centralized Token Creation (app/tokens.py)
- `make_access()` - Primary function for creating access tokens
- `make_refresh()` - Primary function for creating refresh tokens
- `create_access_token()` - **DEPRECATED** - Use `make_access()` instead
- `create_refresh_token()` - **DEPRECATED** - Use `make_refresh()` instead

### ✅ OAuth IdP-Specific Token Signing (Properly Isolated)
- `app/api/oauth_apple.py` - ES256 token signing for Apple OAuth
- `app/api/google_oauth.py` - Google OAuth (no special token signing required)

## Testing Results

### ✅ Deprecation Warnings Working
```
DeprecationWarning: create_access_token is deprecated. Use make_access() instead for better TTL management and claim normalization.
DeprecationWarning: create_refresh_token is deprecated. Use make_refresh() instead for better TTL management and claim normalization.
```

### ✅ New Functions Working
```python
from app.tokens import make_access, make_refresh
access_token = make_access({'user_id': 'test'})  # ✅ Works
refresh_token = make_refresh({'user_id': 'test'})  # ✅ Works
```

### ✅ OAuth Isolation Verified
- Apple OAuth ES256 signing function remains properly isolated
- No interference with centralized token creation

## Benefits Achieved

1. **Centralized Token Management**: All app session token creation goes through `make_access()` and `make_refresh()`
2. **Better TTL Management**: New functions use centralized TTL configuration
3. **Claim Normalization**: Consistent claim handling across the application
4. **Backward Compatibility**: Old functions still work but show deprecation warnings
5. **Proper Isolation**: OAuth IdP-specific token signing remains separate from app session tokens

## Migration Path

Existing code using the deprecated functions should migrate to:
- `create_access_token()` → `make_access()`
- `create_refresh_token()` → `make_refresh()`

The new functions provide better TTL management and claim normalization while maintaining the same basic interface.
