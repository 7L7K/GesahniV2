# Backend Header Mode Authentication Configuration

## Overview
The backend is already fully configured to handle header mode authentication with Bearer token authentication. The system automatically detects Authorization headers and processes them appropriately.

## ✅ **Already Working - No Changes Needed**

### 1. Authorization Header Processing
**File**: `app/deps/user.py` - `get_current_user_id()`

The backend automatically:
- ✅ **Detects Authorization headers**: Checks for `Authorization: Bearer <token>` first
- ✅ **Extracts Bearer tokens**: Parses the token from the Authorization header
- ✅ **Validates JWT tokens**: Verifies tokens against JWT secret or Clerk JWKS
- ✅ **Extracts user identifier**: Gets stable user ID from `sub` claim
- ✅ **Attaches to request state**: Sets `request.state.user_id` for route handlers

**Token Processing Order**:
1. `Authorization: Bearer <token>` header (header mode)
2. WebSocket query parameter `access_token=<token>`
3. `access_token` cookie (cookie mode fallback)
4. `__session` cookie (legacy fallback)

### 2. CSRF Protection Bypass
**File**: `app/csrf.py` - `CSRFMiddleware`

The CSRF middleware automatically:
- ✅ **Bypasses CSRF when Authorization header present**: No CSRF checks for header auth
- ✅ **Logs bypass events**: Records when CSRF is bypassed due to Authorization header
- ✅ **Maintains security**: Still enforces CSRF for cookie-based authentication

**Bypass Logic**:
```python
# Bypass CSRF when Authorization header is present (header auth mode)
auth_header = request.headers.get("Authorization")
if auth_header and auth_header.startswith("Bearer "):
    logger.info("bypass: csrf_authorization_header_present header=<%s>",
               auth_header[:8] + "..." if auth_header else "None")
    return await call_next(request)
```

### 3. CORS Configuration
**File**: `app/main.py` - CORS Middleware

The CORS configuration already:
- ✅ **Allows Authorization header**: `allow_headers=["*"]` includes Authorization
- ✅ **Supports cross-origin requests**: Properly configured for frontend-backend communication
- ✅ **Handles preflight requests**: OPTIONS requests work correctly

**CORS Configuration**:
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=allow_credentials,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],  # Includes Authorization header
    expose_headers=["X-Request-ID"],
    max_age=600,
)
```

### 4. Clerk JWT Support
**File**: `app/deps/clerk_auth.py`

The Clerk authentication module already:
- ✅ **Verifies Clerk JWTs**: Validates tokens against JWKS (public keys)
- ✅ **Extracts user identifier**: Gets user ID from `sub` claim
- ✅ **Supports Authorization headers**: Extracts tokens from Authorization header
- ✅ **Handles WebSocket authentication**: Supports WebSocket token authentication

**Clerk Token Verification**:
```python
def verify_clerk_token(token: str) -> Dict[str, Any]:
    client, iss, aud = _jwks_client()
    signing_key = client.get_signing_key_from_jwt(token)
    claims = jwt.decode(token, signing_key.key, algorithms=["RS256"],
                       options={"require": ["exp", "iat", "sub"]})
    return claims
```

### 5. Public /v1/whoami Endpoint
**File**: `app/api/auth.py`

The `/v1/whoami` endpoint already:
- ✅ **Remains public**: No authentication required
- ✅ **Returns authentication status**: Shows `is_authenticated: false` without token
- ✅ **Supports header authentication**: Returns user info when valid token provided

## 🔧 **Configuration Required**

### Clerk Environment Variables
To enable Clerk JWT verification, set these environment variables in `env.localhost`:

```bash
# Clerk Configuration (for header auth mode)
CLERK_JWKS_URL=https://your-tenant.clerk.accounts.dev/.well-known/jwks.json
CLERK_ISSUER=https://your-tenant.clerk.accounts.dev
CLERK_DOMAIN=your-tenant.clerk.accounts.dev
CLERK_AUDIENCE=your-clerk-publishable-key
```

**Note**: If Clerk is not configured, the backend will fall back to traditional JWT authentication using `JWT_SECRET`.

## 🔄 **Authentication Flow**

### Header Mode Flow:
1. **Frontend sends request** with `Authorization: Bearer <token>` header
2. **Backend detects Authorization header** and bypasses CSRF checks
3. **Token validation**:
   - If Clerk configured: Validates against Clerk JWKS
   - If traditional JWT: Validates against `JWT_SECRET`
4. **User extraction**: Gets user ID from `sub` claim
5. **Request processing**: Attaches user ID to `request.state.user_id`
6. **Route handler**: Receives authenticated user context

### WebSocket Authentication:
1. **Frontend connects** with `access_token=<token>` query parameter
2. **Backend extracts token** from WebSocket query params
3. **Token validation**: Same process as HTTP requests
4. **Connection established**: WebSocket authenticated and ready

## 📋 **Testing the Configuration**

### Test with curl:
```bash
# Test without token (should return 401 for protected endpoints)
curl -X GET http://10.0.0.138:8000/v1/whoami

# Test with invalid token (should return 401)
curl -X GET http://10.0.0.138:8000/v1/whoami \
  -H "Authorization: Bearer invalid_token"

# Test with valid token (should return user info)
curl -X GET http://10.0.0.138:8000/v1/whoami \
  -H "Authorization: Bearer your_valid_token"
```

### Test CORS:
```bash
# Test CORS preflight with Authorization header
curl -X OPTIONS http://10.0.0.138:8000/v1/whoami \
  -H "Origin: http://localhost:3000" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: Authorization"
```

## 🎯 **Key Benefits**

1. **Automatic Detection**: Backend automatically detects and processes Authorization headers
2. **Security**: CSRF protection bypassed appropriately for header auth
3. **Flexibility**: Supports both traditional JWT and Clerk JWT tokens
4. **WebSocket Support**: Full WebSocket authentication support
5. **CORS Ready**: Properly configured for cross-origin requests
6. **Backward Compatible**: Still supports cookie-based authentication

## 📝 **Summary**

The backend is **already fully configured** for header mode authentication. The system:

- ✅ Automatically processes `Authorization: Bearer <token>` headers
- ✅ Bypasses CSRF checks when Authorization header is present
- ✅ Allows Authorization header in CORS configuration
- ✅ Supports both traditional JWT and Clerk JWT validation
- ✅ Extracts stable user identifiers from token claims
- ✅ Maintains `/v1/whoami` as a public endpoint

**No backend code changes are required** - the system is ready for header mode authentication as soon as the frontend sends requests with Authorization headers.
